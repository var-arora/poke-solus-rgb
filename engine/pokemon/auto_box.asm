FindNextBoxWithSpace:
; Return the next box index in a, or carry if every other box is full.
; Do not change boxes or write saved data when a ball might fail.
	ld a, [wCurrentBoxNum]
	and $7f
	ld c, a
	ld d, NUM_BOXES - 1
.nextBox
	inc c
	ld a, c
	cp NUM_BOXES
	jr c, .checkBox
	ld c, 0
.checkBox
	ld a, [wCurrentBoxNum]
	bit 7, a
	jr z, .found ; other boxes are empty before the first box change
	push de
	push bc
	ld a, c
	call AutoBoxSRAMLocation
	call AutoBoxOpenSRAM
	ld a, [hl]
	cp MONS_PER_BOX
	push af
	call AutoBoxCloseSRAM
	pop af
	pop bc
	pop de
	jr c, .found
	dec d
	jr nz, .nextBox
	scf
	ret
.found
	ld a, c
	and a
	ret

AutoChangeBox:
; Called only after a successful capture with a full party.
	ld a, [wBoxCount]
	cp MONS_PER_BOX
	ret c
	call FindNextBoxWithSpace
	ret c ; the ball-use check has already ruled this out
	push af
	ld a, [wCurrentBoxNum]
	inc a
	ld [wAutoBoxChangePending], a
; Keep the full working box in unused SRAM until the map is restored.
	ld b, BANK(sAutoBoxBuffer)
	call AutoBoxOpenSRAM
	ld hl, wBoxDataStart
	ld de, sAutoBoxBuffer
	ld bc, wBoxDataEnd - wBoxDataStart
	call CopyData
	call AutoBoxCloseSRAM
	pop af
	or $80
	ld [wCurrentBoxNum], a
	ld a, [wAutoBoxChangePending]
	dec a
	bit 7, a
	jr z, .firstChange
; Leave the source intact so a reset can still load the previous save.
	call GetBoxSRAMLocation
	call AutoBoxOpenSRAM
	ld de, wBoxDataStart
	ld bc, wBoxDataEnd - wBoxDataStart
	call CopyData
	jp AutoBoxCloseSRAM
.firstChange
	ld hl, wBoxDataStart
	ld bc, wBoxDataEnd - wBoxDataStart
	xor a
	call FillMemory
	ld a, $ff
	ld [wBoxSpecies], a
	ret

FinishAutoBoxChange::
; Run after the map script, so static encounters also finish their events.
	ld a, [wAutoBoxChangePending]
	and a
	ret z
	ld a, [wIsInBattle]
	and a
	ret nz
	ld a, [wAutoBoxChangePending]
	dec a
	bit 7, a
	push af
	call z, EmptyAllSRAMBoxes
	pop af
	and $7f
	call AutoBoxSRAMLocation
	ld d, h
	ld e, l
	call AutoBoxOpenSRAM
; Copy between SRAM banks without replacing the new working box in WRAM.
	ld hl, sAutoBoxBuffer
.copyOldBox
	ld a, BANK(sAutoBoxBuffer)
	ld [MBC1SRamBank], a
	ld a, [hli]
	push af
	ld a, b
	ld [MBC1SRamBank], a
	pop af
	ld [de], a
	inc de
	ld a, l
	cp LOW(sAutoBoxBufferEnd)
	jr nz, .copyOldBox
	ld a, h
	cp HIGH(sAutoBoxBufferEnd)
	jr nz, .copyOldBox
	call AutoBoxUpdateChecksums
	call AutoBoxCloseSRAM
; The old full box is stored before the main save changes the active index.
	call SaveSAVtoSRAM
; Match the normal box-switch convention: the active SRAM slot is empty.
	call GetBoxSRAMLocation
	call AutoBoxOpenSRAM
	call EmptySRAMBox
	call AutoBoxUpdateChecksums
	call AutoBoxCloseSRAM
	xor a
	ld [wAutoBoxChangePending], a
	ld a, [wCurrentBoxNum]
	and $7f
	inc a
	ld [wStringBuffer], a
	tx_pre AutoBoxChangedText
	ld a, SFX_SAVE
	call PlaySoundWaitForCurrent
	jp WaitForSoundToFinish

AutoBoxSRAMLocation:
; Like GetBoxSRAMLocation, but take the box index in a.
	ld b, 2
	cp NUM_BOXES / 2
	jr c, .bankReady
	inc b
	sub NUM_BOXES / 2
.bankReady
	ld hl, BoxSRAMPointerTable
	ld e, a
	ld d, 0
	add hl, de
	add hl, de
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ret

AutoBoxOpenSRAM:
	ld a, SRAM_ENABLE
	ld [MBC1SRamEnable], a
	ld a, 1
	ld [MBC1SRamBankingMode], a
	ld a, b
	ld [MBC1SRamBank], a
	ret

AutoBoxCloseSRAM:
	xor a
	ld [MBC1SRamBankingMode], a
	ld [MBC1SRamEnable], a
	ret

AutoBoxUpdateChecksums:
	ld hl, sBox1 ; sBox7 in bank 3
	ld bc, sBank2AllBoxesChecksum - sBox1
	call SAVCheckSum
	ld [sBank2AllBoxesChecksum], a
	jp CalcIndividualBoxCheckSums

AutoBoxChangedText::
	text "Now using BOX @"
	text_decimal wStringBuffer, 1, 2
	text "."
	line "Game saved."
	prompt
