InitExpandedBag::
	xor a
	ld [wNumBagItems], a
	dec a
	ld [wBagItems], a
	jp SetBagSaveVersion

LoadMainDataAndBag:
	call CopyData
	ld hl, wBagSaveVersion
	ld de, BagSaveVersion
	ld b, 4
.checkVersion
	ld a, [de]
	inc de
	cp [hl]
	jr nz, .importLegacyBag
	inc hl
	dec b
	jr nz, .checkVersion
	ret
.importLegacyBag
; Old saves have only the original 20 slots. Import all of their bag bytes,
; including the terminator. Nothing is written to SRAM until the player saves.
	ld hl, wLegacyNumBagItems
	ld de, wNumBagItems
	ld bc, LEGACY_BAG_ITEM_CAPACITY * 2 + 2
	call CopyData
	jp SetBagSaveVersion

SaveMainDataAndBag:
	push bc
	push de
	push hl
	call SetBagSaveVersion
; Older ROMs can safely read the first 20 slots. Their original bag must not
; contain a count above 20 or continue into money and other saved fields.
	ld a, [wNumBagItems]
	cp LEGACY_BAG_ITEM_CAPACITY
	jr c, .copyLegacyBag
	ld a, LEGACY_BAG_ITEM_CAPACITY
.copyLegacyBag
	ld [wLegacyNumBagItems], a
	add a
	inc a
	ld c, a
	ld b, 0
	ld hl, wBagItems
	ld de, wLegacyBagItems
	call CopyData
	dec de
	ld a, $ff
	ld [de], a
	pop hl
	pop de
	pop bc
	jp CopyData

SetBagSaveVersion:
	ld hl, BagSaveVersion
	ld de, wBagSaveVersion
	ld bc, 4
	jp CopyData

BagSaveVersion:
	db $42, $41, $47, $01 ; bag format 1
