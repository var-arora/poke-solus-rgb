# Gameplay fixes for Solus 1.5

This build includes:

- Normal critical-hit rates match Gen 1. Focus Energy quadruples those rates,
  up to 255/256 (about 99.6%).
- Effectiveness messages and hit sounds use the combined result against both
  defending types. A weakness and resistance that cancel give no effectiveness
  message and use the normal hit sound.
- When the active box is full, a successful capture switches to the next box
  with space. The game saves after the battle and map events finish.
- The bag holds 40 item slots instead of 20. Each slot still holds up to 99
  items, and the PC still holds 50 item slots.

The game still supports the original Game Boy. Its CGB header flag is `00`.
The source build keeps upstream's `.gbc` filenames; a byte-identical copy can
use `.gb` without changing the game.

## Download a patch

Choose the column that matches your input ROM. Every patch in a row produces
the same updated ROM for that color. All inputs and outputs are 1,048,576 bytes.

| Version | Clean original ROM | Official Solus 1.5 | Earlier critical-hit fix | Earlier critical-hit and type fixes | Earlier automatic box fix |
| --- | --- | --- | --- | --- | --- |
| Red | [Red patch](../patches/gameplay-fixes/pokesolusred-1.5-gameplay-fixes.bps), for Pokémon Red | [Red update](../patches/gameplay-fixes/pokesolusred-1.5-to-gameplay-fixes.bps) | [Red update](../patches/gameplay-fixes/pokesolusred-crit-fix-to-gameplay-fixes.bps) | [Red update](../patches/gameplay-fixes/pokesolusred-crit-and-type-fixes-to-gameplay-fixes.bps) | [Red update](../patches/gameplay-fixes/pokesolusred-auto-box-to-gameplay-fixes.bps) |
| Green | [Green patch](../patches/gameplay-fixes/pokesolusgreen-1.5-gameplay-fixes.bps), for Pokémon Red | [Green update](../patches/gameplay-fixes/pokesolusgreen-1.5-to-gameplay-fixes.bps) | [Green update](../patches/gameplay-fixes/pokesolusgreen-crit-fix-to-gameplay-fixes.bps) | [Green update](../patches/gameplay-fixes/pokesolusgreen-crit-and-type-fixes-to-gameplay-fixes.bps) | [Green update](../patches/gameplay-fixes/pokesolusgreen-auto-box-to-gameplay-fixes.bps) |
| Blue | [Blue patch](../patches/gameplay-fixes/pokesolusblue-1.5-gameplay-fixes.bps), for Pokémon Blue | [Blue update](../patches/gameplay-fixes/pokesolusblue-1.5-to-gameplay-fixes.bps) | [Blue update](../patches/gameplay-fixes/pokesolusblue-crit-fix-to-gameplay-fixes.bps) | [Blue update](../patches/gameplay-fixes/pokesolusblue-crit-and-type-fixes-to-gameplay-fixes.bps) | [Blue update](../patches/gameplay-fixes/pokesolusblue-auto-box-to-gameplay-fixes.bps) |

Download the patch with GitHub's **Download raw file** button. Apply it with
[Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) or
[Floating IPS](https://github.com/Alcaro/Flips). BPS patchers check that the input
ROM matches. Do not apply more than one patch from a row.

For the earlier 60-slot build, use its update patch:
[Red](../patches/gameplay-fixes/pokesolusred-60-slot-to-gameplay-fixes.bps),
[Green](../patches/gameplay-fixes/pokesolusgreen-60-slot-to-gameplay-fixes.bps), or
[Blue](../patches/gameplay-fixes/pokesolusblue-60-slot-to-gameplay-fixes.bps).

Input ROM checksums:

| Input | Red | Green | Blue |
| --- | --- | --- | --- |
| Clean original ROM, SHA-1 | `ea9bcae617fdf159b045185467ae58b2e4a48b9a` | Same as Red | `d7037c83e1ae5b39bde3c30787637ba1d4c48ce2` |
| Official Solus 1.5, CRC32 | `4d0b49cb` | `22b4efd5` | `031e86e5` |
| Earlier critical-hit fix, CRC32 | `df7b71b6` | `86ccaecd` | `3545034f` |
| Earlier critical-hit and type fixes, CRC32 | `24743609` | `f5452102` | `a921c774` |
| Earlier automatic box fix, CRC32 | `33a2f3ed` | `b254a8c4` | `83f97551` |
| Earlier 60-slot bag, CRC32 | `ecce1cfd` | `d318ffd2` | `8deec30a` |

Patch-file SHA-256 checksums are in
[SHA256SUMS](../patches/gameplay-fixes/SHA256SUMS).

## Continue a saved game

Existing Solus 1.5 in-game saves remain compatible, including saves made with
the earlier critical-hit, type, and automatic box fixes. The game imports the
old bag into its larger storage area when loading. Money, Pokémon, progress,
and all other existing save fields keep their locations. Cartridge settings
and the 32 KiB save-file size are unchanged. No separate save conversion is
needed.

1. Make an in-game save in your current ROM.
2. Back up the save file, usually a `.sav` file.
3. Replace or patch the ROM. Keep its base filename the same as the save file,
   or import the save with your emulator's save-file option.
4. Start the updated ROM and choose **Continue**.

Emulator save states store the running game and its code addresses. They are
separate from in-game saves and are not covered by these compatibility checks.
Use an in-game save when changing ROM versions.

## Larger bag

The bag has 40 slots. This includes key items and TMs, which still use the same
list as other items. Item use, buying, selling, tossing, swapping, gifts, and
PC transfers use the larger bag. The limit per stack remains 99.

The larger bag uses 126 bytes from an unused 134-byte gap in the main saved
data. It stays inside the existing save checksum. A four-byte format marker
distinguishes it from an old save. When the marker is absent, the loader copies
the original bag, including item order and quantities, into the new area.
Loading does not write to the save file. New games start with an empty bag.

Saves from the earlier 60-slot build keep every item. If such a save has more
than 40 slots in use, no new slot can be added until the count falls below 40.
Existing stacks can still be used or increased, up to 99. The storage area stays
the same size to keep these saves intact.

Saving also keeps the first 20 slots in the original bag fields, with a valid
count and terminator. Older ROMs can read those slots, but cannot maintain the
larger bag. Keep using this build after saving, or restore a backup made before
the upgrade when returning to an older ROM.

The implementation is in
[`expanded_bag.asm`](../engine/items/expanded_bag.asm). Only the bag's working
RAM labels move; every other existing RAM label keeps its address. The original
save code changes two main-data copy calls to add bag import and storage.

## Automatic box changes

With a full party, a full active box no longer prevents a capture if another
box has space. The search starts at the next box, skips full boxes, and wraps
from Box 12 to Box 1. The switch happens only after a successful catch. Failed
throws keep the active box and do not save the game.

After the capture, the game finishes the battle and the map's event script,
saves the game, and shows the new box number. This also saves party health,
used balls, and progress. Ordinary captures that do not change boxes still use
manual saving. Gifts and PC deposits keep their existing behavior.

If the party and all 12 boxes are full, the game refuses the throw without
using a ball. The old man's demonstration still works. Safari captures use
the same automatic box search and consume a Safari Ball.

Gen 1 keeps the active box in working RAM. Its normal box-change routine also
saves, which makes it unsuitable for a direct call during a battle. The new
code keeps the old full box in an unused part of the existing 32 KiB save
memory. It reads the next box without clearing its saved copy. Before the
automatic save begins, the previous saved game remains intact, including
when the player resets at the nickname prompt.

Once the map and its events are ready, the old full box is written to its
normal slot. The normal save routine commits the new active box and game
progress. Box checksums are updated. The temporary area is outside the saved
game's checksum and was unused in Solus 1.5. A new temporary RAM flag uses an
existing unused byte. The box changes do not move any original RAM or save field.

The implementation is in [`auto_box.asm`](../engine/pokemon/auto_box.asm).

## Effectiveness reporting

The original routine applies each type modifier to damage, but overwrites the
reported effectiveness with each matching entry in the type chart. Messages
and hit sounds therefore use the last matching entry, even when the two types
cancel each other.

The fix combines the reporting value while keeping the damage calculation and
its rounding unchanged. The same-type attack bonus remains separate from type
effectiveness. An immunity keeps the combined result at zero.

| Attack type | Defending types | Combined result | Message | Hit sound |
| --- | --- | --- | --- | --- |
| Fighting | Normal / Flying | 1× | None | Normal |
| Grass | Water / Poison | 1× | None | Normal |
| Ice | Water / Flying | 1× | None | Normal |
| Fire | Bug / Grass | 4× | Super effective | Super effective |
| Fire | Water / Rock | ¼× | Not very effective | Not very effective |
| Electric | Water / Ground | 0× | Doesn't affect | None |
| Ground | Bug / Flying | 0× | Doesn't affect | None |

Single-type defenders are counted once. Reversing the order of a defender's
types does not change its reported effectiveness. The existing type chart is
unchanged, including Solus's Ghost-versus-Psychic fix.

The calculation is in
[`AdjustDamageForMoveType`](../engine/battle/core.asm). Both
[`DisplayEffectiveness`](../engine/battle/display_effectiveness.asm) and
[`PlayApplyingAttackSound`](../engine/battle/animations.asm) already read the
same reporting value, so they both receive the corrected result.

For details of the critical-hit calculation, see the
[critical-hit fix guide](CRITICAL-HITS.md#what-changed).

## Build and test

Use RGBDS 0.8.0, then build the ROMs and install the test tools:

```sh
make -j8 red blue green
python3 -m venv /tmp/solus-tests
/tmp/solus-tests/bin/pip install -r tests/requirements.txt
```

Build unmodified upstream commit
`95e157191e920162a24908cc95c358e73d294689` in a separate directory with the same
RGBDS version. Keep its `.sym` files beside its ROMs. Run:

```sh
/tmp/solus-tests/bin/python tests/type_effectiveness.py \
    --original-dir /path/to/unmodified-solus-build
/tmp/solus-tests/bin/python tests/critical_hits.py \
    pokesolusred.gbc pokesolusgreen.gbc pokesolusblue.gbc
/tmp/solus-tests/bin/python tests/save_compatibility.py \
    --original-dir /path/to/unmodified-solus-build
/tmp/solus-tests/bin/python tests/auto_box.py \
    --original-dir /path/to/unmodified-solus-build
/tmp/solus-tests/bin/python tests/expanded_bag.py \
    --original-dir /path/to/unmodified-solus-build \
    --previous-dir /path/to/automatic-box-build \
    --larger-bag-dir /path/to/60-slot-build
```

The effectiveness test runs the compiled damage-adjustment, message-selection,
and hit-sound routines. It checks all 15 attack types against every ordered pair
of the 15 defending types, including single-type pairs. It covers both battle
sides, no same-type attack bonus, a bonus from either attacker type, and seven
starting damage values from 2 to 999. Each color passes 141,750 damage and
effectiveness cases. Damage, miss flags, and the same-type attack bonus are
compared with the unmodified ROM. The type chart must also match.

Another 28 cases per color check the message and hit-sound selectors for each
combined effectiveness value, both battle sides, and the same-type bonus flag
on and off. Printing and audio playback are replaced with test hooks that
inspect the selected text, sound ID, frequency, and tempo. The original damage
math runs unchanged inside the emulator. The test edits only the emulator's
private ROM copy.

The critical-hit tests and disposable-save checks also pass for all three
colors. They cover party data, items, money, badges, progress, all 12 PC boxes,
and continuing before and after saving again. Each patch was applied to its
stated input and checked against the built ROM, byte for byte.

The box tests run the compiled ball-use and capture code with disposable
official saves. They check existing Pokémon records, skipped boxes, wraparound,
the first box change, Safari Balls, failed throws, full storage, and resets
before the automatic save. Saves made after a switch also load and save again
in the original Solus 1.5 ROM. A complete playthrough test uses the real menus,
capture animation, nickname prompt, box notice, automatic save, and Continue.

The bag tests import empty and full 20-slot saves from official Solus 1.5 and
the automatic-box build. They fill all 40 slots through the inventory code,
check stack limits and the unchanged PC limit, remove and combine slots,
swap the first and last slots, and check new-game setup. A real battle-menu
playthrough scrolls to slot 40, uses its ball, finishes a capture and automatic
box save, and checks every remaining item after Continue. Save checks allow
changes only in the unused bag area and the main checksum when importing an
old bag; all other saved fields and every PC box must match.
Saves with all 60 slots from the earlier build also load without losing items;
the tests check that they cannot add a new slot until fewer than 40 remain.

| Updated ROM | CRC32 | SHA-256 |
| --- | --- | --- |
| Red | `eed3741b` | `681bd49057b1b5395b4c233af6d2c7ae527e642ece614f7ca6ffe806ce11af08` |
| Green | `6ff683cf` | `67d85115bf95ccad73df705e691f7be84a0107ce13f99c482b713c0e770d5adc` |
| Blue | `34d313ee` | `ee2e59af1e9a83533cfdc3ccfe5644a6f8aacd18cdd838a027a46f0dcc5232cc` |
