RunMapScriptAndSaveAutoBox:
	call RunMapScript
	ld a, [wAutoBoxChangePending]
	and a
	ret z
	farjp FinishAutoBoxChange
