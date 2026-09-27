;******************************************************************************
; Safwan Kamal
; SEPTEMBER 2026
; TFT4_Bench - hardware benchmark for the tft4 driver
;   Runs the same 14 scenes as the emulator suite (bench_tft4_vs_ti/suite.py)
;   on the real panel and measures each frame: drawing + present + LcdWait.
;   S1 (P1.1): run the next scene, then show its result on the TFT
;   S2 (P1.2): run all scenes, then show a summary table on the TFT
;   Each scene: 1 warm-up frame + 64 timed frames, at most 25 frames/s
;   (the pacing wait is not timed). The segment LCD shows the scene number
;   and its average time in ms, e.g. "03 15.3".
;******************************************************************************

;------------------------------------------------------------------------------
; Register usage notes
;------------------------------------------------------------------------------
; R10 = scene table entry of the scene being run (also in ScenePtr)
; R9  = frame start time (TA1R) while a frame is timed
; R4-R8 are loop counters/pointers inside the subroutines, which save them.
; The tft4 routines keep R4-R10; R11-R15 are scratch and pass arguments.
;------------------------------------------------------------------------------

	.cdecls C,LIST,"msp430.h"       ; Include device header file

	.def    RESET                   ; Export program entry-point to
					; make it known to linker.
	.ref    ClockInit, LcdInit, LcdPresent, LcdPresentFull, LcdWait
	.ref    FbClear, FbFillRect, FbPixel, FbText, FbBlit, FbSaveBg
	.ref    FbRestore, PaletteSet
	.ref    SceneTable, SceneCount, BgOps, DigTab, PalAnim

;-------------------------------------------------------------------------------
	.global _main
	.global __STACK_END
	.sect   .stack                  ; Make stack linker segment known

;------------------------------------------------------------------------------
;           Settings
;------------------------------------------------------------------------------
FRAMES          .set    64              ; timed frames per scene (power of 2)
FRAME_SHIFT     .set    6               ; log2(FRAMES), for the average
MAX_SPR         .set    32              ; most moving sprites in a scene
NUM_PIX         .set    64              ; pixels in the pixel scene
MAX_SCENES      .set    16

; Scene table entry (bench_data.asm)
S_KIND          .set    0
S_NAME          .set    2
S_SPR           .set    4
S_COUNT         .set    6
S_INIT          .set    8
S_XMIN          .set    10
S_YMIN          .set    12
S_XMAX          .set    14
S_YMAX          .set    16
SCENE_SIZE      .set    18

; Colors (palette indices, see DefaultPalette in tft4.asm)
SKY             .set    1               ; Navy
WHITE           .set    7
YELLOW          .set    10
GREEN           .set    11
PEACH           .set    15
SKY_RGB         .set    0x194A          ; default Navy, put back after the
                                        ; palette scene
TXT_ON_SKY      .set    SKY << 8        ; FbText background = sky

	.include "tft4_config.inc"      ; CLOCK_MHZ (the driver's settings)

;------------------------------------------------------------------------------
;           Constants
;------------------------------------------------------------------------------
	.sect 	".const"

FramePeriod	.word   40000           ; 25 Hz at SMCLK/8 = 1 MHz

; What each scene kind does before a frame (not timed) and in it (timed)
PrepTab	.word   PrepNone, PrepMovers, PrepHud, PrepPixels
	.word   PrepFill, PrepStripes, PrepPalette
DrawTab	.word   DrawIdle, DrawMovers, DrawHud, DrawPixels
	.word   DrawFill, DrawStripes, DrawPalette

; Texts (FbText strings end with a 0 byte)
TxTitle	.byte   "tft4 benchmark", 0
TxScene	.byte   "Scene ", 0
TxOf	.byte   " of ", 0
TxAvg	.byte   "avg  ", 0
TxWorst	.byte   "worst", 0
TxMs	.byte   " ms", 0
	.if CLOCK_MHZ > 8
TxFrames	.byte   "64 frames, 16 MHz", 0
	.else
TxFrames	.byte   "64 frames, 8 MHz", 0
	.endif
TxS1	.byte   "S1: next scene", 0
TxS2	.byte   "S2: run all scenes", 0
TxSumHead	.byte   "   scene       avg ms", 0
TxStart	.byte   "Press S1 or S2", 0
	.align  2

; Segment LCD: for each position (0 = rightmost) the LCDM register that gets
; the low byte and the one that gets the high byte of the pattern.
; Same layout as LCDWrite in Pong_Assembly.
SegTable	.word   LCDM9, LCDM8
	.word   LCDM16, LCDM15
	.word   LCDM20, LCDM19
	.word   LCDM5, LCDM4
	.word   LCDM7, LCDM6
	.word   LCDM11, LCDM10

SEGA        .set    1000000000000000b
SEGB        .set    0100000000000000b
SEGC        .set    0010000000000000b
SEGD        .set    0001000000000000b
SEGE        .set    0000100000000000b
SEGF        .set    0000010000000000b
SEGG        .set    0000001000000000b
SEGM        .set    0000000100000000b
SEGH        .set    0000000010000000b
SEGK        .set    0000000000100000b
SEGQ        .set    0000000000001000b
SEGN        .set    0000000000000010b
SEGDP       .set    0000000000000001b

SEG_SPACE   .set    10                  ; index after the 10 digits
SEG_DASH    .set    11

DIGIT:      .word   SEGA+SEGB+SEGC+SEGD+SEGE+SEGF ; 0
            .word   SEGB+SEGC   ; 1
            .word   SEGA+SEGB+SEGD+SEGE+SEGG+SEGM ; 2
            .word   SEGA+SEGB+SEGC+SEGD+SEGG+SEGM   ;3
            .word   SEGB+SEGC+SEGF+SEGG+SEGM    ; 4
            .word   SEGA+SEGC+SEGD+SEGF+SEGG+SEGM   ; 5
            .word   SEGA+SEGC+SEGD+SEGE+SEGF+SEGG+SEGM ; 6
            .word   SEGA+SEGB+SEGC  ; 7
            .word   SEGA+SEGB+SEGC+SEGD+SEGE+SEGF+SEGG+SEGM ; 8
            .word   SEGA+SEGB+SEGC+SEGD+SEGF+SEGG+SEGM ; 9
            .word   0           ; space
            .word   SEGG+SEGM   ; -

;------------------------------------------------------------------------------
;           Variables
;------------------------------------------------------------------------------
	.bss    SprX, MAX_SPR*2, 2      ; moving sprites: place and speed
	.bss    SprY, MAX_SPR*2, 2
	.bss    SprDX, MAX_SPR*2, 2
	.bss    SprDY, MAX_SPR*2, 2
	.bss    OldX, MAX_SPR*2, 2      ; place in the previous frame (erase)
	.bss    OldY, MAX_SPR*2, 2
	.bss    PixX, NUM_PIX, 2        ; pixel scene: this frame's pixels
	.bss    PixY, NUM_PIX, 2
	.bss    PixC, NUM_PIX, 2
	.bss    OldPX, NUM_PIX, 2       ; and the previous frame's
	.bss    OldPY, NUM_PIX, 2
	.bss    ScenePtr, 2, 2
	.bss    SceneNo, 2, 2           ; next scene S1 runs
	.bss    FrameNo, 2, 2           ; 0 = warm-up frame
	.bss    SumLo, 2, 2             ; sum of the timed frames, Timer1 ticks
	.bss    SumHi, 2, 2
	.bss    Worst, 2, 2
	.bss    Param, 2, 2             ; per frame: fill color, stripe offset
	.bss    Rng, 2, 2               ; xorshift16 state (pixel scene)
	.bss    HudLo, 2, 2             ; HUD counter, BCD, 5 digits
	.bss    HudHi, 2, 2
	.bss    AvgHund, MAX_SCENES*2, 2   ; results, hundredths of a ms
	.bss    WorstHund, MAX_SCENES*2, 2
	.bss    NumBuf, 8, 2            ; number text
	.bss    ButtonS1, 2, 2          ; set by PORT1_ISR, cleared by Mainloop
	.bss    ButtonS2, 2, 2

	.text                           ; Assemble to Flash memory
	.retain                         ; Ensure current section gets linked
	.retainrefs

_main
RESET	mov.w   #__STACK_END,SP         ; Initialize stackpointer
StopWDT	mov.w   #WDTPW+WDTHOLD,&WDTCTL  ; Stop WDT

;------------------------------------------------------------------------------
;           Setup
;------------------------------------------------------------------------------
EditClock:
	call    #ClockInit              ; MCLK = SMCLK = CLOCK_MHZ (tft4.asm)

SetupButtons:
	bic.b   #BIT2+BIT1, &P1DIR      ; P1.2 and P1.1 as inputs
	bis.b   #BIT2+BIT1, &P1REN      ; Enable pull resistors
	bis.b   #BIT2+BIT1, &P1OUT      ; Select pull-up mode
	bis.b   #BIT2+BIT1, &P1IES      ; Interrupt on high-to-low edge

UnlockGPIO:
	bic.w   #LOCKLPM5,&PM5CTL0      ; Disable the GPIO power-on default
					; high-impedance mode
	bic.b   #BIT2+BIT1, &P1IFG      ; Clear old interrupt flags
	bis.b   #BIT2+BIT1, &P1IE       ; Enable button interrupts

LCD_SETUP:                              ; on-board segment LCD (from Pong)
	mov.w   #1111111111000000b, &LCDCPCTL0 ; Enable specific segments
	mov.w   #1111000000111111b, &LCDCPCTL1 ; (only the 6 digits)
	mov.w   #0000000011110000b, &LCDCPCTL2 ;
	bis.w   #LCDPRE__16+LCD4MUX, &LCDCCTL0 ; ACLK/16/2=1024Hz
	bis.w   #LCDCLRM, &LCDCMEMCTL          ; Clear LCD memory
	bis.w   #LCDON, &LCDCCTL0              ; Turn the LCD ON

SetupTimers:
	; Timer0_A: frame pacing tick, polled (CCIFG), no interrupt
	mov.w   &FramePeriod, &TA0CCR0
	mov.w   #CLOCK_MHZ/8-1, &TA0EX0 ; SMCLK / 8 / (CLOCK_MHZ / 8) = 1 MHz
	mov.w   #TASSEL__SMCLK+ID__8+MC__UP+TACLR, &TA0CTL
	; Timer1_A: free running 2 us counter for the timing
	; (SMCLK / 8 / 2 = 500 kHz: a 16-bit count covers up to 131 ms)
	mov.w   #CLOCK_MHZ/4-1, &TA1EX0 ; SMCLK / 8 / (CLOCK_MHZ / 4) = 500 kHz
	mov.w   #TASSEL__SMCLK+ID__8+MC__CONTINUOUS+TACLR, &TA1CTL

SetupDriver:
	call    #LcdInit                ; SPI, panel init, black screen

	clr.w   &SceneNo
	clr.w   &ButtonS1
	clr.w   &ButtonS2
	call    #ShowStart

	nop
	eint
	nop

;------------------------------------------------------------------------------
;           Main loop
;------------------------------------------------------------------------------
Mainloop:
	tst.w   &ButtonS1
	jnz     DoNext
	tst.w   &ButtonS2
	jnz     DoAll
	jmp     Mainloop

DoNext	mov.w   &SceneNo, R12
	call    #RunScene
	mov.w   &SceneNo, R12
	inc.w   &SceneNo                ; next time: the next scene
	cmp.w   &SceneCount, &SceneNo
	jlo     ShowIt
	clr.w   &SceneNo
ShowIt	call    #ShowResult             ; R12 = the scene just run
	jmp     Buttons

DoAll	clr.w   R12
AllLoop	push.w  R12
	call    #RunScene
	pop.w   R12
	inc.w   R12
	cmp.w   &SceneCount, R12
	jlo     AllLoop
	clr.w   &SceneNo
	call    #ShowSummary

Buttons	clr.w   &ButtonS1               ; presses during a run don't count
	clr.w   &ButtonS2
	jmp     Mainloop

;------------------------------------------------------------------------------
;           Running a scene
;------------------------------------------------------------------------------

; RunScene: R12 = scene number. Draws the background, runs the warm-up frame
; and FRAMES timed frames, stores the result in AvgHund/WorstHund and shows
; it on the segment LCD.
RunScene:
	push.w  R4
	push.w  R9
	push.w  R10
	mov.w   R12, R4                 ; R4 = scene number
	mov.w   R12, R10                ; R10 = SceneTable + number * 18
	rla.w   R10
	mov.w   R10, R13
	rla.w   R10
	rla.w   R10
	rla.w   R10                     ; number * 16
	add.w   R13, R10                ; + number * 2
	add.w   #SceneTable, R10
	mov.w   R10, &ScenePtr

	mov.w   R4, R12                 ; segment LCD: "nn ----" while running
	mov.w   #0xFFFF, R13
	call    #ShowSeg

	call    #DrawBackground
	call    #FbSaveBg
	call    #LcdPresentFull
	call    #LcdWait

	clr.w   &FrameNo
	clr.w   &SumLo
	clr.w   &SumHi
	clr.w   &Worst
	mov.w   #0xACE1, &Rng           ; same start as suite.py
	mov.w   #0x2345, &HudLo         ; counter starts at 12345
	mov.w   #0x0001, &HudHi
	cmp.w   #1, S_KIND(R10)
	jne     FrameLoop
	call    #StartMovers

FrameLoop
	bit.w   #CCIFG, &TA0CCTL0       ; at most 25 frames per second
	jz      FrameLoop
	bic.w   #CCIFG, &TA0CCTL0

	mov.w   S_KIND(R10), R15        ; untimed: move things, pick colors
	rla.w   R15
	mov.w   PrepTab(R15), R15
	call    R15

	mov.w   &TA1R, R9               ; timed: draw + present + wait
	mov.w   S_KIND(R10), R15
	rla.w   R15
	mov.w   DrawTab(R15), R15
	call    R15
	mov.w   &TA1R, R12
	sub.w   R9, R12                 ; R12 = frame time, 2 us ticks

	tst.w   &FrameNo
	jz      FrameDone               ; warm-up frame: not counted
	add.w   R12, &SumLo
	addc.w  #0, &SumHi
	cmp.w   &Worst, R12
	jlo     FrameDone
	mov.w   R12, &Worst
FrameDone
	inc.w   &FrameNo
	cmp.w   #FRAMES+1, &FrameNo
	jlo     FrameLoop

	cmp.w   #6, S_KIND(R10)         ; palette scene: put the sky color back
	jne     Results
	mov.w   #SKY, R12
	mov.w   #SKY_RGB, R13
	call    #PaletteSet
	call    #LcdPresentFull         ; unchanged pixels still show the old
	call    #LcdWait                ; color on the glass: send them all

Results	mov.w   #FRAME_SHIFT, R13       ; average = sum / FRAMES
AvgShift	clrc
	rrc.w   &SumHi
	rrc.w   &SumLo
	dec.w   R13
	jnz     AvgShift
	mov.w   &SumLo, R12
	call    #TicksToHund_sr
	mov.w   R4, R13
	rla.w   R13
	mov.w   R12, AvgHund(R13)
	mov.w   &Worst, R12
	call    #TicksToHund_sr
	mov.w   R4, R13
	rla.w   R13
	mov.w   R12, WorstHund(R13)

	mov.w   AvgHund(R13), R13       ; segment LCD: number + average
	mov.w   R4, R12
	call    #ShowSeg
	pop.w   R10
	pop.w   R9
	pop.w   R4
	ret

; DrawBackground: sky, stars, ground, grass (BgOps)
DrawBackground:
	push.w  R4
	mov.w   #BgOps, R4
BgLoop	cmp.w   #0xFFFF, 0(R4)
	jeq     BgDone
	mov.w   @R4+, R12
	mov.w   @R4+, R13
	mov.w   @R4+, R14
	mov.w   @R4+, R15
	call    #FbFillRect
	jmp     BgLoop
BgDone	pop.w   R4
	ret

; StartMovers: copy the start table (x, y, dx, dy per sprite) of the scene
StartMovers:
	mov.w   S_INIT(R10), R14
	mov.w   S_COUNT(R10), R15
	clr.w   R13
StartLoop
	mov.w   @R14+, SprX(R13)
	mov.w   @R14+, SprY(R13)
	mov.w   @R14+, SprDX(R13)
	mov.w   @R14+, SprDY(R13)
	incd.w  R13
	dec.w   R15
	jnz     StartLoop
	ret

;------------------------------------------------------------------------------
;           Before each frame (not timed). R10 = scene.
;------------------------------------------------------------------------------
PrepNone:
	ret

; PrepMovers: remember where every sprite is (to erase it), then move it and
; bounce off the box (like suite.py: flip the speed, clamp the place).
; Frame 0 draws the start places.
PrepMovers:
	push.w  R4
	push.w  R5
	clr.w   R4
	mov.w   S_COUNT(R10), R5
	rla.w   R5                      ; R5 = end of the arrays
MovLoop	mov.w   SprX(R4), OldX(R4)
	mov.w   SprY(R4), OldY(R4)
	tst.w   &FrameNo
	jz      MovNext
	add.w   SprDX(R4), SprX(R4)
	cmp.w   S_XMIN(R10), SprX(R4)   ; x < x min? (signed)
	jl      MovXLow
	cmp.w   SprX(R4), S_XMAX(R10)   ; x > x max?
	jge     MovY
	mov.w   S_XMAX(R10), SprX(R4)
	jmp     MovXFlip
MovXLow	mov.w   S_XMIN(R10), SprX(R4)
MovXFlip	xor.w   #0xFFFF, SprDX(R4)      ; negate: invert and add 1
	inc.w   SprDX(R4)
MovY	add.w   SprDY(R4), SprY(R4)
	cmp.w   S_YMIN(R10), SprY(R4)
	jl      MovYLow
	cmp.w   SprY(R4), S_YMAX(R10)
	jge     MovNext
	mov.w   S_YMAX(R10), SprY(R4)
	jmp     MovYFlip
MovYLow	mov.w   S_YMIN(R10), SprY(R4)
MovYFlip	xor.w   #0xFFFF, SprDY(R4)
	inc.w   SprDY(R4)
MovNext	incd.w  R4
	cmp.w   R5, R4
	jlo     MovLoop
	pop.w   R5
	pop.w   R4
	ret

; PrepHud: counter + 7 (BCD)
PrepHud:
	clrc
	dadd.w  #0x0007, &HudLo
	dadd.w  #0x0000, &HudHi
	ret

; PrepPixels: keep the previous pixels (to erase them), make 64 new ones:
; x = r & 127, y = r & 127 (again while >= 110), color = 8 + (r & 7)
PrepPixels:
	push.w  R4
	clr.w   R4
PixLoop	mov.b   PixX(R4), OldPX(R4)
	mov.b   PixY(R4), OldPY(R4)
	call    #Rand_sr
	and.w   #127, R12
	mov.b   R12, PixX(R4)
PixNewY	call    #Rand_sr
	and.w   #127, R12
	cmp.w   #110, R12
	jhs     PixNewY
	mov.b   R12, PixY(R4)
	call    #Rand_sr
	and.w   #7, R12
	add.w   #8, R12
	mov.b   R12, PixC(R4)
	inc.w   R4
	cmp.w   #NUM_PIX, R4
	jlo     PixLoop
	pop.w   R4
	ret

; PrepFill: color 2 + frame % 12
PrepFill:
	mov.w   &FrameNo, R12
FillMod	cmp.w   #12, R12
	jlo     FillSet
	sub.w   #12, R12
	jmp     FillMod
FillSet	add.w   #2, R12
	mov.w   R12, &Param
	ret

; PrepStripes: offset = frame % 16
PrepStripes:
	mov.w   &FrameNo, R12
	and.w   #15, R12
	mov.w   R12, &Param
	ret

; PrepPalette: sky color = PalAnim[frame % 4]
PrepPalette:
	mov.w   &FrameNo, R12
	and.w   #3, R12
	rla.w   R12
	mov.w   PalAnim(R12), &Param
	ret

;------------------------------------------------------------------------------
;           The timed part of each frame. R10 = scene.
;------------------------------------------------------------------------------
DrawIdle:
	call    #LcdPresent
	call    #LcdWait
	ret

; DrawMovers: erase every sprite at its old place, draw every sprite at its
; new place (all erased first, so no erase wipes a sprite already drawn)
DrawMovers:
	push.w  R4
	push.w  R5
	push.w  R6
	mov.w   S_COUNT(R10), R5
	rla.w   R5                      ; R5 = end of the arrays
	mov.w   S_SPR(R10), R6          ; R6 = sprite
	tst.w   &FrameNo
	jz      DmDraw                  ; frame 0: nothing to erase yet
	clr.w   R4
DmErase	mov.b   0(R6), R14              ; w + (h << 8)
	mov.b   1(R6), R15
	swpb    R15
	bis.w   R15, R14
	mov.w   OldX(R4), R12
	mov.w   OldY(R4), R13
	call    #FbRestore
	incd.w  R4
	cmp.w   R5, R4
	jlo     DmErase
DmDraw	clr.w   R4
DmBlit	mov.w   R6, R12
	mov.w   SprX(R4), R13
	mov.w   SprY(R4), R14
	call    #FbBlit
	incd.w  R4
	cmp.w   R5, R4
	jlo     DmBlit
	call    #LcdPresent
	call    #LcdWait
	pop.w   R6
	pop.w   R5
	pop.w   R4
	ret

; DrawHud: 5 opaque 6x10 digits at x = 90, 97, .., y = 2
DrawHud:
	push.w  R4
	push.w  R5
	push.w  R6
	mov.w   #90, R4                 ; R4 = x
	mov.w   &HudHi, R12             ; ten-thousands
	and.w   #0x0F, R12
	call    #HudDigit_sr
	mov.w   &HudLo, R5              ; then the 4 BCD digits, top first
	mov.w   #4, R6
HudLoop	mov.w   R5, R12
	swpb    R12
	rra.w   R12
	rra.w   R12
	rra.w   R12
	rra.w   R12
	and.w   #0x0F, R12
	call    #HudDigit_sr
	rla.w   R5
	rla.w   R5
	rla.w   R5
	rla.w   R5
	dec.w   R6
	jnz     HudLoop
	call    #LcdPresent
	call    #LcdWait
	pop.w   R6
	pop.w   R5
	pop.w   R4
	ret

; HudDigit_sr: R12 = digit, R4 = x (moved on by 7)
HudDigit_sr:
	rla.w   R12
	mov.w   DigTab(R12), R12
	mov.w   R4, R13
	mov.w   #2, R14
	call    #FbBlit
	add.w   #7, R4
	ret

; DrawPixels: erase the previous 64 pixels (from the background), draw the new
DrawPixels:
	push.w  R4
	tst.w   &FrameNo
	jz      DpDraw
	clr.w   R4
DpErase	mov.b   OldPX(R4), R12
	mov.b   OldPY(R4), R13
	mov.w   #0x0101, R14            ; 1 x 1
	call    #FbRestore
	inc.w   R4
	cmp.w   #NUM_PIX, R4
	jlo     DpErase
DpDraw	clr.w   R4
DpPixel	mov.b   PixX(R4), R12
	mov.b   PixY(R4), R13
	mov.b   PixC(R4), R14
	call    #FbPixel
	inc.w   R4
	cmp.w   #NUM_PIX, R4
	jlo     DpPixel
	call    #LcdPresent
	call    #LcdWait
	pop.w   R4
	ret

; DrawFill: the whole screen in a new color
DrawFill:
	clr.w   R12
	clr.w   R13
	mov.w   #0x8080, R14            ; 128 x 128
	mov.w   &Param, R15
	call    #FbFillRect
	call    #LcdPresent
	call    #LcdWait
	ret

; DrawStripes: 18 vertical stripes, 8 wide, x = i * 8 - 16 + offset
DrawStripes:
	push.w  R4
	push.w  R5
	mov.w   &Param, R4
	sub.w   #16, R4                 ; R4 = x
	clr.w   R5                      ; R5 = i
StrLoop	mov.w   R4, R12
	clr.w   R13
	mov.w   #0x8008, R14            ; 8 x 128
	mov.w   #12, R15                ; even stripes: Sky blue
	bit.w   #1, R5
	jz      StrFill
	mov.w   #9, R15                 ; odd stripes: Orange
StrFill	call    #FbFillRect
	add.w   #8, R4
	inc.w   R5
	cmp.w   #18, R5
	jlo     StrLoop
	call    #LcdPresent
	call    #LcdWait
	pop.w   R5
	pop.w   R4
	ret

; DrawPalette: change the sky color, then send the whole screen again
DrawPalette:
	mov.w   #SKY, R12
	mov.w   &Param, R13
	call    #PaletteSet
	call    #LcdPresentFull
	call    #LcdWait
	ret

;------------------------------------------------------------------------------
;           Screens
;------------------------------------------------------------------------------

; ShowStart: title and what the buttons do
ShowStart:
	mov.w   #SKY, R12
	call    #FbClear
	mov.w   #TxTitle, R12
	mov.w   #22, R13
	mov.w   #20, R14
	mov.w   #YELLOW+TXT_ON_SKY, R15
	call    #FbText
	mov.w   #TxStart, R12
	mov.w   #22, R13
	mov.w   #50, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	call    #ShowButtons
	call    #LcdPresent
	call    #LcdWait
	ret

; ShowButtons: S1 / S2 help at the bottom, with the name of the next scene
ShowButtons:
	mov.w   #TxS1, R12
	mov.w   #4, R13
	mov.w   #92, R14
	mov.w   #GREEN+TXT_ON_SKY, R15
	call    #FbText
	mov.w   &SceneNo, R12           ; "  (next scene name)"
	call    #SceneName_sr
	mov.w   #22, R13
	mov.w   #102, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	mov.w   #TxS2, R12
	mov.w   #4, R13
	mov.w   #116, R14
	mov.w   #GREEN+TXT_ON_SKY, R15
	call    #FbText
	ret

; ShowResult: R12 = scene number. Name, average and worst frame time.
ShowResult:
	push.w  R4
	push.w  R5
	mov.w   R12, R4
	mov.w   #SKY, R12
	call    #FbClear
	mov.w   #TxTitle, R12
	mov.w   #22, R13
	mov.w   #4, R14
	mov.w   #YELLOW+TXT_ON_SKY, R15
	call    #FbText

	mov.w   #TxScene, R12           ; "Scene 3 of 14"
	mov.w   #4, R13
	mov.w   #20, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	mov.w   R12, R5                 ; x after the text
	mov.w   R4, R12
	inc.w   R12
	call    #FmtInt_sr
	mov.w   R5, R13
	mov.w   #20, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	mov.w   R12, R13
	mov.w   #TxOf, R12
	mov.w   #20, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	mov.w   R12, R5
	mov.w   &SceneCount, R12
	call    #FmtInt_sr
	mov.w   R5, R13
	mov.w   #20, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText

	mov.w   R4, R12                 ; name
	call    #SceneName_sr
	mov.w   #4, R13
	mov.w   #32, R14
	mov.w   #PEACH+TXT_ON_SKY, R15
	call    #FbText

	mov.w   #TxAvg, R12             ; "avg   15.47 ms"
	mov.w   R4, R13
	rla.w   R13
	mov.w   AvgHund(R13), R13
	mov.w   #48, R14
	call    #ShowMsLine_sr
	mov.w   #TxWorst, R12           ; "worst 15.64 ms"
	mov.w   R4, R13
	rla.w   R13
	mov.w   WorstHund(R13), R13
	mov.w   #58, R14
	call    #ShowMsLine_sr
	mov.w   #TxFrames, R12
	mov.w   #4, R13
	mov.w   #70, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText

	call    #ShowButtons
	call    #LcdPresent
	call    #LcdWait
	pop.w   R5
	pop.w   R4
	ret

; ShowMsLine_sr: R12 = label, R13 = hundredths of a ms, R14 = y.
; Draws "label  ddd.dd ms" at x = 4.
ShowMsLine_sr:
	push.w  R4
	push.w  R5
	mov.w   R13, R4
	mov.w   R14, R5
	mov.w   #4, R13
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	push.w  R12                     ; x after the label
	mov.w   R4, R12
	call    #FmtHund_sr
	pop.w   R13
	mov.w   R5, R14
	mov.w   #YELLOW+TXT_ON_SKY, R15
	call    #FbText
	mov.w   R12, R13
	mov.w   #TxMs, R12
	mov.w   R5, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	pop.w   R5
	pop.w   R4
	ret

; ShowSummary: one line per scene: number, name, average ms
ShowSummary:
	push.w  R4
	push.w  R5
	mov.w   #SKY, R12
	call    #FbClear
	mov.w   #TxSumHead, R12
	mov.w   #1, R13
	mov.w   #1, R14
	mov.w   #YELLOW+TXT_ON_SKY, R15
	call    #FbText
	clr.w   R4                      ; R4 = scene
	mov.w   #11, R5                 ; R5 = y
SumLoop	mov.w   R4, R12                 ; number, right aligned in 2
	inc.w   R12
	call    #FmtInt_sr
	mov.w   #1, R13
	cmp.w   #9, R4
	jhs     SumNum
	mov.w   #7, R13                 ; one digit: one column further right
SumNum	mov.w   R5, R14
	mov.w   #WHITE+TXT_ON_SKY, R15
	call    #FbText
	mov.w   R4, R12
	call    #SceneName_sr
	mov.w   #19, R13
	mov.w   R5, R14
	mov.w   #PEACH+TXT_ON_SKY, R15
	call    #FbText
	mov.w   R4, R12
	rla.w   R12
	mov.w   AvgHund(R12), R12
	call    #FmtHund_sr
	mov.w   #91, R13                ; 6 characters: x = 91..126
	mov.w   R5, R14
	mov.w   #YELLOW+TXT_ON_SKY, R15
	call    #FbText
	add.w   #8, R5
	inc.w   R4
	cmp.w   &SceneCount, R4
	jlo     SumLoop
	call    #LcdPresent
	call    #LcdWait
	pop.w   R5
	pop.w   R4
	ret

; SceneName_sr: R12 = scene number -> R12 = its name
SceneName_sr:
	rla.w   R12
	mov.w   R12, R13
	rla.w   R12
	rla.w   R12
	rla.w   R12
	add.w   R13, R12                ; number * 18
	mov.w   SceneTable+S_NAME(R12), R12
	ret

;------------------------------------------------------------------------------
;           Numbers
;------------------------------------------------------------------------------

; TicksToHund_sr: R12 = Timer1 ticks (2 us) -> R12 = hundredths of a ms
; (ticks / 5, rounded)
TicksToHund_sr:
	add.w   #2, R12
	mov.w   #5, R13
	call    #Div16_sr
	ret

; Div16_sr: R12 / R13 -> R12 = quotient, R14 = remainder (unsigned).
; Uses R15.
Div16_sr:
	clr.w   R14
	mov.w   #16, R15
DivLoop	rla.w   R12                     ; next dividend bit into the carry
	rlc.w   R14                     ; and into the remainder
	cmp.w   R13, R14
	jlo     DivNext
	sub.w   R13, R14
	bis.w   #1, R12                 ; quotient bit
DivNext	dec.w   R15
	jnz     DivLoop
	ret

; FmtHund_sr: R12 = hundredths -> NumBuf = "ddd.dd" (6 characters, leading
; zeros as spaces, always "0.dd" at least). Returns R12 = NumBuf.
FmtHund_sr:
	mov.w   #NumBuf+6, R11
	clr.b   0(R11)                  ; end of the string
	mov.w   #10, R13
	call    #Div16_sr               ; hundredths digit
	add.w   #'0', R14
	mov.b   R14, -1(R11)
	call    #Div16_sr               ; tenths
	add.w   #'0', R14
	mov.b   R14, -2(R11)
	mov.b   #'.', -3(R11)
	call    #Div16_sr               ; ones
	add.w   #'0', R14
	mov.b   R14, -4(R11)
	call    #Div16_sr               ; tens
	add.w   #'0', R14
	mov.b   R14, -5(R11)
	call    #Div16_sr               ; hundreds
	add.w   #'0', R14
	mov.b   R14, -6(R11)
	cmp.b   #'0', -6(R11)           ; blank leading zeros
	jne     FmtDone
	mov.b   #' ', -6(R11)
	cmp.b   #'0', -5(R11)
	jne     FmtDone
	mov.b   #' ', -5(R11)
FmtDone	mov.w   #NumBuf, R12
	ret

; FmtInt_sr: R12 = 0..99 -> NumBuf = "d" or "dd". Returns R12 = NumBuf.
FmtInt_sr:
	mov.w   #10, R13
	call    #Div16_sr               ; R12 = tens, R14 = ones
	mov.w   #NumBuf, R11
	tst.w   R12
	jz      FmtOnes
	add.w   #'0', R12
	mov.b   R12, 0(R11)
	inc.w   R11
FmtOnes	add.w   #'0', R14
	mov.b   R14, 0(R11)
	clr.b   1(R11)
	mov.w   #NumBuf, R12
	ret

; Rand_sr: xorshift16 (7, 9, 8) -> R12 = next value. Uses R13.
Rand_sr:
	mov.w   &Rng, R12
	mov.w   R12, R13                ; x ^= x << 7
	rla.w   R13
	rla.w   R13
	rla.w   R13
	rla.w   R13
	rla.w   R13
	rla.w   R13
	rla.w   R13
	xor.w   R13, R12
	mov.w   R12, R13                ; x ^= x >> 9
	swpb    R13
	and.w   #0x00FF, R13
	clrc
	rrc.w   R13
	xor.w   R13, R12
	mov.w   R12, R13                ; x ^= x << 8
	swpb    R13
	and.w   #0xFF00, R13
	xor.w   R13, R12
	mov.w   R12, &Rng
	ret

;------------------------------------------------------------------------------
;           Segment LCD
;------------------------------------------------------------------------------

; ShowSeg: R12 = scene number (0-based, shown from 1), R13 = hundredths of a
; ms, or 0xFFFF for "----". Shows "nn" and the time with one decimal.
ShowSeg:
	push.w  R4
	push.w  R5
	mov.w   R13, R5
	inc.w   R12
	mov.w   #10, R13
	call    #Div16_sr               ; R12 = tens, R14 = ones
	mov.w   R14, R4
	mov.w   R12, R11
	mov.w   #5, R14
	call    #SegChar_sr
	mov.w   R4, R11
	mov.w   #4, R14
	call    #SegChar_sr
	bic.b   #SEGDP, &LCDM16         ; no decimal point yet

	cmp.w   #0xFFFF, R5
	jne     SegTime
	mov.w   #3, R4                  ; "----"
SegDash	mov.w   #SEG_DASH, R11
	mov.w   R4, R14
	call    #SegChar_sr
	dec.w   R4
	jge     SegDash
	jmp     SegDone

SegTime	mov.w   R5, R12                 ; tenths = (hundredths + 5) / 10
	add.w   #5, R12
	mov.w   #10, R13
	call    #Div16_sr
	clr.w   R4                      ; position 0 = rightmost
SegDigit	mov.w   #10, R13
	call    #Div16_sr               ; R14 = next digit
	mov.w   R14, R11
	cmp.w   #2, R4                  ; blank leading zeros, keep "0.x"
	jlo     SegShow
	tst.w   R12
	jnz     SegShow
	tst.w   R14
	jnz     SegShow
	mov.w   #SEG_SPACE, R11
SegShow	push.w  R12
	mov.w   R4, R14
	call    #SegChar_sr
	pop.w   R12
	inc.w   R4
	cmp.w   #4, R4
	jlo     SegDigit
	bis.b   #SEGDP, &LCDM16         ; decimal point after position 1
SegDone	pop.w   R5
	pop.w   R4
	ret

; SegChar_sr: R11 = DIGIT index, R14 = position (0 = rightmost .. 5)
; Keeps R12-R15.
SegChar_sr:
	push.w  R12
	push.w  R15
	rla.w   R11
	mov.w   DIGIT(R11), R11         ; segment pattern
	mov.w   R14, R15
	rla.w   R15
	rla.w   R15                     ; 4 bytes per SegTable entry
	mov.w   SegTable(R15), R12
	mov.b   R11, 0(R12)             ; low byte
	swpb    R11
	mov.w   SegTable+2(R15), R12
	mov.b   R11, 0(R12)             ; high byte
	pop.w   R15
	pop.w   R12
	ret

;------------------------------------------------------------------------------
;           Interrupt Service Routines
;------------------------------------------------------------------------------
PORT1_ISR:
	add.w   &P1IV, PC               ; add offset to PC
	reti                            ; Vector 0: no interrupt
	reti                            ; Vector 2: P1.0
	jmp     S1Pressed               ; Vector 4: P1.1
	jmp     S2Pressed               ; Vector 6: P1.2
	reti                            ; Vector 8: P1.3
	reti                            ; Vector 10: P1.4
	reti                            ; Vector 12: P1.5
	reti                            ; Vector 14: P1.6
	reti                            ; Vector 16: P1.7
S1Pressed
	mov.w   #1, &ButtonS1
	reti
S2Pressed
	mov.w   #1, &ButtonS2
	reti

;------------------------------------------------------------------------------
;           Interrupt Vectors
;------------------------------------------------------------------------------
	.sect       ".reset"                ; MSP430 RESET Vector
	.short      RESET                   ;
	.sect       PORT1_VECTOR            ; Port 1 Vector
	.short      PORT1_ISR               ;
	.end
