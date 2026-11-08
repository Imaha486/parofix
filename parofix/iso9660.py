# -*- coding: utf-8 -*-
"""
最小限の ISO9660 リーダ / パッチャ（PSP UMD イメージ用）

- 外部ライブラリ不要
- 展開: 全ファイルをフォルダへ書き出す
- 差し替え: 元 ISO をコピーし、指定ファイルのデータを置き換える
    * 新しいサイズが元の割り当てセクタ数に収まる → その場で上書き
    * 収まらない → イメージ末尾に追記し、ディレクトリレコードの
      extent / size と PVD の Volume Space Size を更新
  元 ISO の他の部分（UMD_DATA.BIN、ボリューム記述子、他ファイル）は
  バイト単位でそのまま維持されるので、PSP / PPSSPP から見た互換性が高い。
"""
import os
import shutil
import struct

SECTOR = 2048


class IsoEntry:
    __slots__ = ("path", "is_dir", "extent", "size", "record_offset", "flags")

    def __init__(self, path, is_dir, extent, size, record_offset, flags):
        self.path = path            # "/PSP_GAME/USRDIR/..."（ISO 上の表記そのまま。;1 は除去）
        self.is_dir = is_dir
        self.extent = extent        # 先頭セクタ番号
        self.size = size            # バイト数
        self.record_offset = record_offset  # ディレクトリレコードのイメージ内オフセット
        self.flags = flags

    def __repr__(self):
        return f"<IsoEntry {self.path} lba={self.extent} size={self.size}>"


def _strip_version(name: str) -> str:
    if ";" in name:
        name = name.split(";", 1)[0]
    if name.endswith("."):
        name = name[:-1]
    return name


class Iso9660:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.f.seek(16 * SECTOR)
        pvd = self.f.read(SECTOR)
        if pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise ValueError("ISO9660 の Primary Volume Descriptor が見つかりません: %s" % path)
        self.pvd = pvd
        self.volume_space_size = struct.unpack_from("<I", pvd, 80)[0]
        self.system_id = pvd[8:40].decode("ascii", "replace").rstrip()
        self.volume_id = pvd[40:72].decode("ascii", "replace").rstrip()
        root = pvd[156:156 + 34]
        self.root_extent = struct.unpack_from("<I", root, 2)[0]
        self.root_size = struct.unpack_from("<I", root, 10)[0]
        self.entries = {}   # 大文字化したパス → IsoEntry
        self.order = []     # 列挙順
        self._walk("", self.root_extent, self.root_size)

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # --- ディレクトリ走査 ---
    def _walk(self, prefix, extent, size):
        self.f.seek(extent * SECTOR)
        data = self.f.read(size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # セクタ境界のパディング → 次のセクタへ
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            rec = data[pos:pos + rec_len]
            ext = struct.unpack_from("<I", rec, 2)[0]
            sz = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            name_len = rec[32]
            raw_name = rec[33:33 + name_len]
            if raw_name in (b"\x00", b"\x01"):
                pos += rec_len
                continue
            name = _strip_version(raw_name.decode("ascii", "replace"))
            full = prefix + "/" + name
            is_dir = bool(flags & 2)
            e = IsoEntry(full, is_dir, ext, sz, extent * SECTOR + pos, flags)
            self.entries[full.upper()] = e
            self.order.append(e)
            if is_dir:
                self._walk(full, ext, sz)
            pos += rec_len

    # --- 参照 ---
    def find(self, path) -> IsoEntry:
        key = "/" + path.strip("/").replace("\\", "/")
        e = self.entries.get(key.upper())
        if e is None:
            raise FileNotFoundError("ISO 内にファイルがありません: %s" % path)
        return e

    def read(self, path) -> bytes:
        e = self.find(path)
        self.f.seek(e.extent * SECTOR)
        return self.f.read(e.size)

    def files(self):
        return [e for e in self.order if not e.is_dir]

    def extract_all(self, out_dir, progress=None):
        n = 0
        for e in self.files():
            dst = os.path.join(out_dir, e.path.lstrip("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            self.f.seek(e.extent * SECTOR)
            remaining = e.size
            with open(dst, "wb") as o:
                while remaining > 0:
                    chunk = self.f.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    o.write(chunk)
                    remaining -= len(chunk)
            n += 1
            if progress:
                progress(e.path)
        return n


def _alloc_sectors(size):
    return (size + SECTOR - 1) // SECTOR


def _load_replacements(iso, replacements):
    out = {}
    for p, src in replacements.items():
        e = iso.find(p)
        if isinstance(src, (bytes, bytearray)):
            data = bytes(src)
        else:
            with open(src, "rb") as fh:
                data = fh.read()
        out[e.path.upper()] = data
    return out


def rebuild_iso(src_iso, dst_iso, replacements, log=print):
    """
    ファイル領域を詰め直して新しい ISO を作る（既定の方式）。
    先頭のシステム領域・ボリューム記述子・パステーブル・ディレクトリはそのままコピーし、
    ファイル本体だけを元の並び順で連続配置し直す。ディレクトリレコードの extent/size と
    PVD の Volume Space Size を更新する。
    """
    with Iso9660(src_iso) as iso:
        rep = _load_replacements(iso, replacements)
        files = sorted(iso.files(), key=lambda e: e.extent)
        first_lba = min(e.extent for e in files if e.size > 0)
        for e in iso.order:
            if e.record_offset >= first_lba * SECTOR or (e.is_dir and e.extent >= first_lba):
                log("  ディレクトリがファイル領域の後ろにあるため追記方式に切り替えます")
                return patch_iso(src_iso, dst_iso, replacements, log=log)
        iso.f.seek(0)
        header = bytearray(iso.f.read(first_lba * SECTOR))
        log(f"ISO を再構築中: {src_iso} -> {dst_iso}")
        with open(dst_iso, "wb") as out:
            out.write(header)  # 後で上書き
            cursor = first_lba
            for e in files:
                data = rep.get(e.path.upper())
                if data is not None:
                    size = len(data)
                else:
                    size = e.size
                alloc = _alloc_sectors(size)
                lba = cursor if size > 0 else e.extent
                out.seek(cursor * SECTOR)
                if data is not None:
                    out.write(data)
                    log(f"  差し替え: {e.path}  {e.size:,} -> {size:,} bytes  LBA {e.extent} -> {lba}")
                else:
                    iso.f.seek(e.extent * SECTOR)
                    remaining = size
                    while remaining > 0:
                        chunk = iso.f.read(min(4 << 20, remaining))
                        if not chunk:
                            raise IOError("元 ISO の読み込みが途中で終了しました: " + e.path)
                        out.write(chunk)
                        remaining -= len(chunk)
                pad = alloc * SECTOR - size
                if pad:
                    out.write(b"\x00" * pad)
                cursor += alloc
                ro = e.record_offset
                struct.pack_into("<I", header, ro + 2, lba)
                struct.pack_into(">I", header, ro + 6, lba)
                struct.pack_into("<I", header, ro + 10, size)
                struct.pack_into(">I", header, ro + 14, size)
            total = cursor
            struct.pack_into("<I", header, 16 * SECTOR + 80, total)
            struct.pack_into(">I", header, 16 * SECTOR + 84, total)
            out.seek(0)
            out.write(header)
            out.seek(0, os.SEEK_END)
            final = out.tell()
            if final < total * SECTOR:
                out.write(b"\x00" * (total * SECTOR - final))
        log(f"  Volume Space Size: {iso.volume_space_size} -> {total} sectors")
    log(f"完了: {dst_iso} ({os.path.getsize(dst_iso):,} bytes)")
    return dst_iso


def patch_iso(src_iso, dst_iso, replacements, log=print):
    """
    追記方式: src_iso をコピーして dst_iso を作り、指定ファイルを差し替える。
    元の配置を一切動かさないが、入らないファイルは末尾に追記されるため ISO が大きくなる。
    replacements: {"PSP_GAME/USRDIR/....bin": bytes または ファイルパス, ...}
    """
    with Iso9660(src_iso) as iso:
        targets = []
        for p, src in replacements.items():
            e = iso.find(p)
            if isinstance(src, (bytes, bytearray)):
                data = bytes(src)
            else:
                with open(src, "rb") as fh:
                    data = fh.read()
            targets.append((e, data))
        total_sectors = iso.volume_space_size

    log(f"ISO をコピー中: {src_iso} -> {dst_iso}")
    shutil.copyfile(src_iso, dst_iso)

    with open(dst_iso, "r+b") as f:
        f.seek(0, os.SEEK_END)
        img_size = f.tell()
        # 末尾に追記する場合の開始セクタ（イメージ実サイズと PVD の大きい方）
        append_lba = max(_alloc_sectors(img_size), total_sectors)
        new_total = total_sectors

        for e, data in targets:
            old_alloc = _alloc_sectors(e.size)
            new_alloc = _alloc_sectors(len(data))
            if new_alloc <= old_alloc:
                lba = e.extent
                f.seek(lba * SECTOR)
                f.write(data)
                # 旧領域の残りをゼロ埋め
                pad = old_alloc * SECTOR - len(data)
                if pad:
                    f.write(b"\x00" * pad)
                log(f"  差し替え(その場): {e.path}  {e.size} -> {len(data)} bytes  LBA={lba}")
            else:
                lba = append_lba
                f.seek(lba * SECTOR)
                f.write(data)
                pad = new_alloc * SECTOR - len(data)
                if pad:
                    f.write(b"\x00" * pad)
                append_lba += new_alloc
                new_total = max(new_total, append_lba)
                log(f"  差し替え(末尾追記): {e.path}  {e.size} -> {len(data)} bytes  LBA={e.extent} -> {lba}")
            # ディレクトリレコード更新（LE/BE 両方）
            rec = bytearray(34)
            f.seek(e.record_offset)
            rec[:] = f.read(34)
            struct.pack_into("<I", rec, 2, lba)
            struct.pack_into(">I", rec, 6, lba)
            struct.pack_into("<I", rec, 10, len(data))
            struct.pack_into(">I", rec, 14, len(data))
            f.seek(e.record_offset)
            f.write(rec)

        if new_total != total_sectors:
            f.seek(16 * SECTOR + 80)
            f.write(struct.pack("<I", new_total) + struct.pack(">I", new_total))
            log(f"  Volume Space Size: {total_sectors} -> {new_total} sectors")
        f.flush()
        f.seek(0, os.SEEK_END)
        final = f.tell()
        # 2048 境界に揃える
        if final % SECTOR:
            f.write(b"\x00" * (SECTOR - final % SECTOR))
    log(f"完了: {dst_iso} ({os.path.getsize(dst_iso):,} bytes)")
    return dst_iso
