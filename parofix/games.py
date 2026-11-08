# -*- coding: utf-8 -*-
"""パロディウス ポータブル (ULJM-05220) のアーカイブ定義"""
from .encoder import POOL_INGAME, POOL_MENU, POOL_MSX

TARGETS = {
    # key: (ISO 内パス, 説明, 読み込みバッファ上限)
    "paro2": ("PSP_GAME/USRDIR/CDData/sound/BGM/bgm.bin", "パロディウスだ! 〜神話からお笑いへ〜", POOL_INGAME),
    "paro3": ("PSP_GAME/USRDIR/data/sound/BGM/bgm.bin", "実況おしゃべりパロディウス", POOL_INGAME),
    "paro4": ("PSP_GAME/USRDIR/data1/sound/BGM/bgm.bin", "極上パロディウス 〜過去の栄光を求めて〜", POOL_INGAME),
    "paro5": ("PSP_GAME/USRDIR/data/p5/sound/BGM/at3bgm.bin", "セクシーパロディウス", POOL_INGAME),
    "msx": ("PSP_GAME/USRDIR/data/mxs/msx_paro_bgm.bin", "パロディウス (MSX)", POOL_MSX),
    "msx_remix": ("PSP_GAME/USRDIR/data/mxs/msx_bgm_remix.bin", "パロディウス (MSX) リミックス", POOL_MSX),
    "menu": ("PSP_GAME/USRDIR/data/menu/AllBgmbgm.bin", "ミュージックプレイヤーモード（全曲）", POOL_MENU),
}

# bgmcallno.h（ISO 内に残っていた開発用ヘッダ）由来のトラック名
TRACK_NAMES = {
    "paro4": ["01", "02SD_OPEN", "03SD_SELECT", "04SD_AIRBIG", "05SD_AIRTAKO", "06SD_AIRTWIN", "07SD_AIRPEN",
              "08SD_AIRHIKA", "09SD_AIRMAN", "10SD_AIRPIG", "11SD_AIRKOI", "12SD_BGM1", "13SD_BOSS1", "14SD_BGM2",
              "15SD_BOSS2", "16SD_BGM3", "17SD_BGM3B", "18SD_BOSS3", "19SD_BGM4", "20SD_BOSS4", "21SD_BGM5",
              "22SD_BOSS5", "23SD_BOSS6", "24SD_BGM6", "25SD_BOSSTAC", "26SD_BGMUSAGI", "27SD_BOSSKAGU",
              "28SD_BGMMOAI", "29SD_BOSSMOAI", "30SD_BOSSKOORI", "31SD_RANK", "32SD_BGMNEKO2", "33SD_BGMNEKO3",
              "34SD_GAME_OVER", "35SD_CONTINUE", "36THANK", "37SD_OCHI", "38SD_TITLE", "39SD_ENDDEMO1",
              "40SD_ENDDEMO2", "41SD_ENDING", "42SD_SP_STAGE", "43", "44SD_UTA1", "45SD_UTA2", "46_SD_UTA3"],
    "paro3": ["STR0003-GAMEOVER", "STR0004-NAME", "STR0005-NARATION-M", "STR0006-NARATION-W", "STR0007-SELECT",
              "STR0008-BLACK", "STR0009-B_RUSH1", "STR0010-B_RUSH2", "STR0011-ST8SKY", "STR0012-ENDING",
              "STR0013-SKY", "STR0014-SKY2", "STR0015-YUKI", "STR0016-HAKABA", "STR0017-RUBY", "STR0018-MOAI",
              "STR0019-TAINAI", "STR0020-SYOKUBUTU", "STR0021-BOSS", "STR0022-KOUSOUKU", "STR0023-KOUSOUKU2",
              "STR0024-YOUSAI1", "STR0025-YOUSAI2", "STR0026-SE_KEIHOU", "STR0027-LS_BOSS", "STR0028-LS_BOSS2",
              "STR0029", "STR0030"],
    "paro5": ["BGM_SD_A_ACE", "BGM_SD_A_BLACK", "BGM_SD_A_HIKARU", "BGM_SD_A_IVAN", "BGM_SD_A_KOITSU",
              "BGM_SD_A_MANBO", "BGM_SD_A_MIKCAEL", "BGM_SD_A_OPTION", "BGM_SD_A_VIPER", "BGM_SD_BAD_CLR",
              "BGM_SD_BGM_CONT", "BGM_SD_BGM_OVER", "BGM_SD_BGM_RANK", "BGM_SD_BGM_THANK", "BGM_SD_BOSS_SPE",
              "BGM_SD_BOSS_ST1", "BGM_SD_BOSS_ST2", "BGM_SD_BOSS_ST3", "BGM_SD_BOSS_ST4", "BGM_SD_BOSS_ST5",
              "BGM_SD_BOSS_ST6", "BGM_SD_BOSS_ST7", "BGM_SD_BOSS_ST8", "BGM_SD_BOSS_ST9", "BGM_SD_DEMO_ST",
              "BGM_SD_OPENING", "BGM_SD_SELECT", "BGM_SD_SPE", "BGM_SD_ST1", "BGM_SD_ST2", "BGM_SD_ST3",
              "BGM_SD_ST4", "BGM_SD_ST5", "BGM_SD_ST6", "BGM_SD_ST7", "BGM_SD_ST8_B1", "BGM_SD_ST8_B2",
              "BGM_SD_ST8_B3", "BGM_SD_ST8_B4", "BGM_SD_ST9", "BGM_SD_STAFF", "BGM_SD_ST_CLEAR", "BGM_SD_TITLE"],
}

# ゲーム内トラック → ミュージックモード (menu) のトラック番号
# クロマ特徴量による自動照合結果（スコア 0.7 以上のみ）。差し替え時に "also_music_mode": true を
# 指定するとここを参照する。必ずしも完全ではないので、重要な曲は `menu-map` で再確認を推奨。
MENU_MAP = {
    "paro2": {0: 33, 1: 36, 2: 48, 3: 49, 5: 51, 8: 34, 9: 37, 10: 41, 11: 55, 14: 52, 15: 43, 16: 38,
              17: 58, 18: 44, 19: 32, 20: 39, 22: 50, 23: 56, 24: 46, 27: 30, 28: 54, 29: 31, 30: 61,
              31: 62, 32: 60, 33: 31,
              # 以下はスコアが低めだがループ構造が一致（要確認）
              4: 40, 7: 42, 6: 53, 12: 35, 13: 47, 21: 45, 25: 57, 26: 29},
    "paro4": {1: 65, 2: 67, 3: 68, 4: 71, 5: 74, 6: 77, 7: 79, 8: 82, 9: 85, 12: 70, 13: 72, 14: 73,
              17: 76, 18: 78, 19: 92, 20: 80, 21: 81, 22: 91, 23: 90, 24: 92, 25: 86, 26: 87, 27: 83,
              28: 84, 29: 96, 30: 99, 31: 72, 34: 97, 35: 100, 37: 66, 38: 93, 40: 94, 41: 95, 43: 102,
              44: 104, 45: 106,
              # 要確認
              10: 89, 36: 88, 32: 72},
}
