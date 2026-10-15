#!/usr/bin/env python3
"""Check combined effectiveness, text, sound, and unchanged damage with PyBoy."""

import argparse
from io import BytesIO
from itertools import product
from pathlib import Path
from zlib import crc32

from pyboy import PyBoy

from critical_hits import read_symbols
from save_compatibility import Game, ORIGINAL_CRC32


TYPES = (0, 1, 2, 3, 4, 5, 7, 8, 20, 21, 22, 23, 24, 25, 26)
DAMAGE = (2, 3, 7, 10, 255, 256, 999)


def type_chart(rom, symbols):
    bank, address = symbols["TypeEffects"]
    offset = bank * 0x4000 + address % 0x4000
    chart = {}
    while rom[offset] != 0xFF:
        attack, defense, factor = rom[offset:offset + 3]
        assert factor in (0, 5, 20)
        assert (attack, defense) not in chart
        chart[attack, defense] = factor
        offset += 3
    return chart


def run_damage_cases(rom, expected_damage=None):
    symbols = read_symbols(rom.with_suffix(".sym"))
    chart = type_chart(rom.read_bytes(), symbols)
    emulator = PyBoy(str(rom), ram_file=BytesIO(b"\xff" * 32768),
                     window="null", sound_emulated=False)
    emulator.set_emulation_speed(0)
    memory = emulator.memory
    registers = emulator.register_file
    state = {"done": False, "checks": 0}
    results = []
    cases = iter(product(TYPES, TYPES, TYPES, range(2), range(3), DAMAGE))

    def address(name):
        return symbols[name][1]

    # Call the actual damage routine from a driver in the emulator's private
    # ROM copy. Its multiplication and division routines remain intact.
    bank, entry = symbols["AdjustDamageForMoveType"]
    memory[0, 0x100:0x108] = [0xF3, 0xCD, entry & 0xFF, entry >> 8,
                             0x00, 0xC3, 0x01, 0x01]
    memory[0xFF50] = 1
    memory[0xFFFF] = 0
    memory[0xFF40] = 0
    memory[0xFF07] = 0
    memory[0x2000] = bank
    memory[address("hLoadedROMBank")] = bank
    registers.SP = 0xDFFF
    registers.PC = 0x100

    def stop_driver():
        state["done"] = True
        memory[0, 0x105:0x108] = [0x76, 0x18, 0xFD]

    def next_case():
        try:
            attack, first, second, side, stab, damage = next(cases)
        except StopIteration:
            stop_driver()
            return
        other = TYPES[(TYPES.index(attack) + 1) % len(TYPES)]
        attacker = (other, other) if stab == 0 else (attack, attack) if stab == 1 else (other, attack)
        player, enemy = (attacker, (first, second)) if side == 0 else ((first, second), attacker)
        for name, data in (("wBattleMonType", player), ("wEnemyMonType", enemy),
                           ("wDamage", (damage >> 8, damage & 0xFF))):
            start = address(name)
            memory[start:start + 2] = list(data)
        memory[address("wPlayerMoveType")] = attack if side == 0 else other
        memory[address("wEnemyMoveType")] = attack if side else other
        memory[address("hWhoseTurn")] = side
        memory[address("wDamageMultipliers")] = 10
        memory[address("wMoveMissed")] = 0
        factor = chart.get((attack, first), 10)
        if second != first:
            factor = factor * chart.get((attack, second), 10) // 10
        state.update(case=(attack, first, second, side, stab, damage),
                     factor=factor, stab=0x80 if stab else 0)

    def after_damage(_):
        if state["done"]:
            return
        try:
            start = address("wDamage")
            damage = memory[start] * 256 + memory[start + 1]
            missed = memory[address("wMoveMissed")]
            multiplier = memory[address("wDamageMultipliers")]
            actual = (damage, missed, multiplier & 0x80)
            if expected_damage is None:
                results.append(actual)
            else:
                assert actual == expected_damage[state["checks"]], (state["case"], "Damage or miss behavior changed", actual)
                assert multiplier == (state["factor"] | state["stab"]), (state["case"], "Wrong combined effectiveness", multiplier)
            state["checks"] += 1
            next_case()
        except Exception as error:
            # PyBoy can swallow hook exceptions. Raise the saved error after tick.
            state["error"] = error
            stop_driver()

    emulator.hook_register(0, 0x104, after_damage, None)
    next_case()
    try:
        previous_checks = -1
        unchanged_frames = 0
        for _ in range(100000):
            emulator.tick(1, False)
            if state["done"]:
                break
            unchanged_frames = unchanged_frames + 1 if state["checks"] == previous_checks else 0
            assert unchanged_frames < 3, (state["case"], "Test driver stopped returning")
            previous_checks = state["checks"]
        if "error" in state:
            raise state["error"]
        assert state["done"], "Type-effectiveness checks did not finish"
        assert state["checks"] == len(TYPES) ** 3 * 2 * 3 * len(DAMAGE)
    finally:
        emulator.stop(save=False)
    return results, chart, state["checks"]


def check_messages_and_sounds(rom):
    game = Game(rom)
    texts, sounds = [], []
    checks = 0
    try:
        # Inspect the selected output while leaving the message and sound
        # selectors intact. Each routine call starts in its own ROM bank.
        for name in ("PrintText", "PlaySound", "WaitForSoundToFinish"):
            bank, entry = game.symbols[name]
            game.memory[bank, entry] = 0xC9
        game.emulator.hook_register(*game.symbols["PrintText"],
                                     lambda _: texts.append(game.emulator.register_file.HL), None)
        game.emulator.hook_register(*game.symbols["PlaySound"],
                                     lambda _: sounds.append((game.emulator.register_file.A,
                                                               game.read("wFrequencyModifier")[0],
                                                               game.read("wTempoModifier")[0])), None)
        sound_ids = {name: (game.address(label) - game.address("SFX_Headers_1")) // 3
                     for name, label in (("neutral", "SFX_Damage"),
                                         ("resist", "SFX_Not_Very_Effective"),
                                         ("super", "SFX_Super_Effective"))}
        for side, stab, factor in product(range(2), (0, 0x80), (0, 2, 5, 10, 20, 40)):
            game.write("hWhoseTurn", side)
            game.write("wPlayerMoveEffect", 0)
            game.write("wEnemyMoveEffect", 0)
            game.write("wCriticalHitOrOHKO", 0)
            game.write("wDamageMultipliers", factor | stab)
            texts.clear()
            if factor == 0:
                game.call("PrintMoveFailureText")
                expected_text = "DoesntAffectMonText"
            else:
                game.call("DisplayEffectiveness")
                expected_text = None if factor == 10 else "SuperEffectiveText" if factor > 10 else "NotVeryEffectiveText"
            assert texts == ([] if expected_text is None else [game.address(expected_text)]), (side, stab, factor, "Wrong text", texts)
            sounds.clear()
            game.call("PlayApplyingAttackSound")
            expected_sound = ([] if factor == 0 else
                              [(sound_ids["neutral"], 0x20, 0x30)] if factor == 10 else
                              [(sound_ids["super"], 0xE0, 0xFF)] if factor > 10 else
                              [(sound_ids["resist"], 0x50, 0x01)])
            assert sounds == expected_sound, (side, stab, factor, "Wrong sound", sounds)
            checks += 1
            if factor == 2:
                # Existing quarter-damage rounding can reduce damage to zero.
                # It remains a miss, distinct from a type immunity.
                texts.clear()
                game.call("PrintMoveFailureText")
                assert texts == [game.address("AttackMissedText")]
                checks += 1
    finally:
        game.stop()
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, required=True,
                        help="Directory with unmodified Solus 1.5 ROMs and .sym files")
    parser.add_argument("--fixed-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    for color in ("red", "green", "blue"):
        name = f"pokesolus{color}.gbc"
        original, fixed = args.original_dir / name, args.fixed_dir / name
        assert crc32(original.read_bytes()) == ORIGINAL_CRC32[color], "Input must be official Solus 1.5"
        print(f"{color}: comparing all type pairs with the original damage routine", flush=True)
        baseline, chart, _ = run_damage_cases(original)
        _, fixed_chart, count = run_damage_cases(fixed, baseline)
        assert chart == fixed_chart, "The type chart changed"
        reports = check_messages_and_sounds(fixed)
        assert reports == 28
        print(f"{color}: {count:,} damage cases and {reports} message/sound cases passed", flush=True)
