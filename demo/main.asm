;******************************************************************************
; Safwan Kamal
; SEPTEMBER 2026
; tft4 demo + benchmark
;   Bouncing sprites over a static scene, drawn with the tft4 driver in
;   retained mode: the scene is drawn once and saved as the background; each
;   frame only erases the sprites (FbRestore) and draws them again.
;   S1 (P1.1): switch between delta present (D) and full present (F)
;   S2 (P1.2): switch between 4 and 12 sprites
;   The on-board segment LCD shows the mode (d = delta, F = full) and how
;   long the last present took in milliseconds, e.g. "d  12.6" or "F  65.6".
;******************************************************************************

;------------------------------------------------------------------------------
; Register usage notes
;------------------------------------------------------------------------------
; R4  = sprite loop index (word offset into the sprite arrays)
; R5  = sprite count * 2 (end of the sprite arrays)
; R6  = present start time (TA1R)
; R7  = frame counter (segment LCD refresh)
; The tft4 routines keep R4-R10, so these survive every driver call.
; R11-R15 are scratch and are used to pass arguments (R12, R13, R14, R15).
;------------------------------------------------------------------------------

	.cdecls C,LIST,"msp430.h"       ; Include device header file

	.def    RESET                   ; Export program entry-point to
					; make it known to linker.
	.ref    ClockInit, LcdInit, LcdPresent, LcdPresentFull, LcdWait
	.ref    FbClear, FbFillRect, FbBlit, FbSaveBg, FbRestoreSpr
	.ref    SprCrab, SprSquid, SprOctopus, SprShip, SprBall, SprHeart, SprUfo

;-------------------------------------------------------------------------------
	.global _main
	.global __STACK_END
	.sect   .stack                  ; Make stack linker segment ?known?

	.include "tft4_config.inc"      ; CLOCK_MHZ (the driver's settings)

;------------------------------------------------------------------------------
;           Constants
;------------------------------------------------------------------------------
	.sect 	".const"

FramePeriod	.word   40000           ; 25 Hz at SMCLK/8 = 1 MHz
MaxSprites	.word   12
FewSprites	.word   4
SegRefresh	.word   8               ; update the segment LCD every 8 frames

; Colors (palette indices, see DefaultPalette in tft4.asm)
SkyColor	.word   1               ; Navy
GroundColor	.word   3               ; DkGreen
GrassColor	.word   11              ; Green
StarColor	.word   7               ; White

; Sprite for each slot, start position and speed
SprTable	.word   SprCrab, SprSquid, SprOctopus, SprShip, SprBall, SprHeart
	.word   SprUfo, SprCrab, SprSquid, SprOctopus, SprBall, SprHeart
StartX	.word   5, 30, 60, 90, 110, 15, 45, 75, 100, 20, 55, 85
StartY	.word   15, 25, 35, 45, 55, 65, 75, 85, 95, 40, 60, 20
StartDX	.word   1, -2, 2, -1, 3, -3, 1, 2, -2, 1, -1, 3
StartDY	.word   2, 1, -1, 2, -2, 1, -3, 1, 2, -1, 3, -2

; Stars: x, y pairs (static background detail)
Stars	.word   10, 14,  34, 22,  58, 9,  81, 30,  102, 16,  121, 40
	.word   7, 52,  46, 61,  70, 47,  93, 70,  117, 83,  25, 90
StarCount	.word   12

; Decimal places for the segment LCD number (tenths of a millisecond)
DecTable	.word   1000, 100, 10, 1
TicksPerTenth	.word   50              ; Timer1 ticks are 2 us

; Segment LCD: for each position (0 = rightmost) the LCDM register that gets
; the low byte and the one that gets the high byte of the pattern.
; Same layout as LCDWrite in Pong_Assembly.
SegTable	.word   LCDM9, LCDM8
	.word   LCDM16, LCDM15
	.word   LCDM20, LCDM19
	.word   LCDM5, LCDM4
	.word   LCDM7, LCDM6
	.word   LCDM11, LCDM10

; LED CONSTS (from Pong_Assembly)
; High Segments
SEGA        .set    1000000000000000b
SEGB        .set    0100000000000000b
SEGC        .set    0010000000000000b
SEGD        .set    0001000000000000b
SEGE        .set    0000100000000000b
SEGF        .set    0000010000000000b
SEGG        .set    0000001000000000b
SEGM        .set    0000000100000000b
; Low Segments (MSB padded)
SEGH        .set    0000000010000000b
SEGJ        .set    0000000001000000b
SEGK        .set    0000000000100000b
SEGP        .set    0000000000010000b
SEGQ        .set    0000000000001000b
SEGN        .set    0000000000000010b
SEGDP       .set    0000000000000001b

CHAR_F      .set    5
CHAR_SPACE  .set    26
CHAR_DIGIT0 .set    27
CHAR_d      .set    37                  ; lower-case d, added after the digits

CHAR:       .word   SEGA+SEGB+SEGC+SEGE+SEGF+SEGG+SEGM ; A
            .word   SEGA+SEGD+SEGE+SEGF+SEGG+SEGK+SEGN ; B
            .word   SEGA+SEGD+SEGE+SEGF ; C
            .word   SEGA+SEGB+SEGC+SEGD+SEGE+SEGF ; D
            .word   SEGA+SEGD+SEGE+SEGF+SEGG+SEGM ; E
            .word   SEGA+SEGE+SEGF+SEGG+SEGM ; F
            .word   SEGA+SEGC+SEGD+SEGE+SEGF+SEGM ; G
            .word   SEGB+SEGC+SEGE+SEGF+SEGG+SEGM ; H
            .word   SEGA+SEGD+SEGJ+SEGP ; I
            .word   SEGA+SEGB+SEGC+SEGD+SEGE ; J
            .word   SEGE+SEGF+SEGG+SEGK+SEGN ; K
            .word   SEGD+SEGE+SEGF ; L
            .word   SEGB+SEGC+SEGE+SEGF+SEGH+SEGK ; M
            .word   SEGB+SEGC+SEGE+SEGF+SEGH+SEGN ; N
            .word   SEGA+SEGB+SEGC+SEGD+SEGE+SEGF+SEGH+SEGK+SEGQ+SEGN ; O
            .word   SEGA+SEGB+SEGE+SEGF+SEGG+SEGM ; P
            .word   SEGA+SEGB+SEGC+SEGD+SEGE+SEGF+SEGN ; Q
            .word   SEGA+SEGB+SEGE+SEGF+SEGG+SEGM+SEGN ; R
            .word   SEGA+SEGC+SEGD+SEGF+SEGG+SEGM ; S
            .word   SEGA+SEGJ+SEGP ; T
            .word   SEGB+SEGC+SEGD+SEGE+SEGF ; U
            .word   SEGE+SEGF+SEGQ+SEGK ; V
            .word   SEGB+SEGC+SEGE+SEGF+SEGQ+SEGN ; W
            .word   SEGH+SEGK+SEGQ+SEGN ; X
            .word   SEGH+SEGK+SEGP ; Y
            .word   SEGA+SEGD+SEGK+SEGQ ; Z
SPACE:      .word   0       ; Space
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
LOWER_D:    .word   SEGB+SEGC+SEGD+SEGE+SEGG+SEGM ; d (the D above looks like 0)

;------------------------------------------------------------------------------
;           Variables
;------------------------------------------------------------------------------
	.bss    SprX, 24, 2
	.bss    SprY, 24, 2
	.bss    SprDX, 24, 2
	.bss    SprDY, 24, 2
	.bss    SprCount, 2, 2          ; sprites on screen * 2 (array end)
	.bss    FullMode, 2, 2          ; 0 = LcdPresent, 1 = LcdPresentFull
	.bss    PresentTime, 2, 2       ; last present, Timer1 ticks (2 us)
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
	; Timer0_A: frame tick, polled (CCIFG), no interrupt
	mov.w   &FramePeriod, &TA0CCR0
	mov.w   #CLOCK_MHZ/8-1, &TA0EX0 ; SMCLK / 8 / (CLOCK_MHZ / 8) = 1 MHz
	mov.w   #TASSEL__SMCLK+ID__8+MC__UP+TACLR, &TA0CTL
	; Timer1_A: free running 2 us counter for the benchmark
	; (SMCLK / 8 / 2 = 500 kHz: a 16-bit count covers up to 131 ms)
	mov.w   #CLOCK_MHZ/4-1, &TA1EX0 ; SMCLK / 8 / (CLOCK_MHZ / 4) = 500 kHz
	mov.w   #TASSEL__SMCLK+ID__8+MC__CONTINUOUS+TACLR, &TA1CTL

SetupDriver:
	call    #LcdInit                ; SPI, panel init, black screen

SetupSprites:
	clr.w   R4
InitSprLoop
	mov.w   StartX(R4), SprX(R4)
	mov.w   StartY(R4), SprY(R4)
	mov.w   StartDX(R4), SprDX(R4)
	mov.w   StartDY(R4), SprDY(R4)
	incd.w  R4
	cmp.w   #24, R4
	jlo     InitSprLoop
	mov.w   &MaxSprites, R5
	rla.w   R5
	mov.w   R5, &SprCount
	clr.w   &FullMode
	clr.w   &ButtonS1
	clr.w   &ButtonS2
	clr.w   R7

	call    #DrawBackground         ; static scene, once
	call    #FbSaveBg
	call    #DrawSprites
	call    #LcdPresentFull

	nop
	eint
	nop

;------------------------------------------------------------------------------
;           Main loop
;------------------------------------------------------------------------------
Mainloop:
WaitFrame
	bit.w   #CCIFG, &TA0CCTL0       ; wait for the 25 Hz tick
	jz      WaitFrame
	bic.w   #CCIFG, &TA0CCTL0

	call    #EraseSprites           ; old places, with the old sprite count
	call    #HandleButtons
	call    #MoveSprites
	call    #DrawSprites

	mov.w   &TA1R, R6               ; time the present
	tst.w   &FullMode
	jnz     DoFull
	call    #LcdPresent
	jmp     PresentDone
DoFull	call    #LcdPresentFull
PresentDone
	call    #LcdWait                ; count until the last byte is out
	mov.w   &TA1R, R12
	sub.w   R6, R12
	mov.w   R12, &PresentTime

	inc.w   R7
	cmp.w   &SegRefresh, R7
	jlo     Mainloop
	clr.w   R7
	call    #ShowPresentTime
	jmp     Mainloop

;------------------------------------------------------------------------------
;           Subroutines
;------------------------------------------------------------------------------

; HandleButtons: S1 toggles full/delta present, S2 toggles 4/12 sprites
HandleButtons:
	tst.w   &ButtonS1
	jz      CheckS2
	clr.w   &ButtonS1
	xor.w   #1, &FullMode
CheckS2	tst.w   &ButtonS2
	jz      ButtonsDone
	clr.w   &ButtonS2
	mov.w   &FewSprites, R12
	rla.w   R12
	cmp.w   R12, &SprCount
	jne     SetFew
	mov.w   &MaxSprites, R12
	rla.w   R12
SetFew	mov.w   R12, &SprCount
ButtonsDone
	ret

; MoveSprites: move every sprite, bounce off the walls and the ground
MoveSprites:
	clr.w   R4
	mov.w   &SprCount, R5
MoveLoop
	add.w   SprDX(R4), SprX(R4)
	cmp.w   #2, SprX(R4)            ; left wall (signed)
	jge     CheckRight
	mov.w   #2, SprX(R4)
	call    #FlipDX
CheckRight
	cmp.w   #112, SprX(R4)          ; right wall (sprites are <= 15 wide)
	jl      MoveY
	mov.w   #111, SprX(R4)
	call    #FlipDX
MoveY
	add.w   SprDY(R4), SprY(R4)
	cmp.w   #2, SprY(R4)            ; top
	jge     CheckGround
	mov.w   #2, SprY(R4)
	call    #FlipDY
CheckGround
	cmp.w   #104, SprY(R4)          ; ground at y = 112, sprites are 8 tall
	jl      MoveNext
	mov.w   #103, SprY(R4)
	call    #FlipDY
MoveNext
	incd.w  R4
	cmp.w   R5, R4
	jlo     MoveLoop
	ret

FlipDX:
	xor.w   #0xFFFF, SprDX(R4)      ; negate: invert and add 1
	inc.w   SprDX(R4)
	ret

FlipDY:
	xor.w   #0xFFFF, SprDY(R4)
	inc.w   SprDY(R4)
	ret

; DrawBackground: sky, stars, ground (drawn once, then saved with FbSaveBg)
DrawBackground:
	mov.w   &SkyColor, R12
	call    #FbClear

	clr.w   R4                      ; stars: 1x1 rectangles
StarLoop
	mov.w   Stars(R4), R12
	mov.w   Stars+2(R4), R13
	mov.w   #0x0101, R14            ; w = 1, h = 1
	mov.w   &StarColor, R15
	call    #FbFillRect
	add.w   #4, R4
	mov.w   &StarCount, R12
	rla.w   R12
	rla.w   R12
	cmp.w   R12, R4
	jlo     StarLoop

	clr.w   R12                     ; ground: 128 x 16 at y = 112
	mov.w   #112, R13
	mov.w   #0x1080, R14            ; w = 128, h = 16
	mov.w   &GroundColor, R15
	call    #FbFillRect
	clr.w   R12                     ; grass line
	mov.w   #112, R13
	mov.w   #0x0280, R14            ; w = 128, h = 2
	mov.w   &GrassColor, R15
	call    #FbFillRect
	ret

; EraseSprites: put the background back where each sprite is now
EraseSprites:
	clr.w   R4
	mov.w   &SprCount, R5
EraseLoop
	mov.w   SprTable(R4), R12       ; FbRestoreSpr reads the sprite's size
	mov.w   SprX(R4), R13
	mov.w   SprY(R4), R14
	call    #FbRestoreSpr
	incd.w  R4
	cmp.w   R5, R4
	jlo     EraseLoop
	ret

; DrawSprites: every sprite at its current place
DrawSprites:
	clr.w   R4
	mov.w   &SprCount, R5
DrawSprLoop
	mov.w   SprTable(R4), R12
	mov.w   SprX(R4), R13
	mov.w   SprY(R4), R14
	call    #FbBlit
	incd.w  R4
	cmp.w   R5, R4
	jlo     DrawSprLoop
	ret

; ShowPresentTime: "d" or "F" on the left, then the time as ms with one
; decimal ("  12.6"). Uses R11-R15.
ShowPresentTime:
	mov.w   #CHAR_d, R11
	tst.w   &FullMode
	jz      ShowMode
	mov.w   #CHAR_F, R11
ShowMode
	mov.w   #5, R14                 ; leftmost position
	call    #SegChar_sr
	mov.w   #CHAR_SPACE, R11
	mov.w   #4, R14
	call    #SegChar_sr

	mov.w   &PresentTime, R13       ; ticks -> tenths of a ms (divide by 50)
	clr.w   R12
TenthsLoop
	cmp.w   &TicksPerTenth, R13
	jlo     TenthsDone
	sub.w   &TicksPerTenth, R13
	inc.w   R12
	jmp     TenthsLoop
TenthsDone
	push.w  R8                      ; R8 = 1 once a digit has been shown
	clr.w   R8
	mov.w   #DecTable, R13
	mov.w   #3, R14                 ; 4 digits: positions 3..0
DigitLoop
	clr.w   R15
DigitSub
	cmp.w   @R13, R12               ; R12 >= place value?
	jlo     DigitOut
	sub.w   @R13, R12
	inc.w   R15
	jmp     DigitSub
DigitOut
	mov.w   R15, R11
	add.w   #CHAR_DIGIT0, R11
	bis.w   R15, R8                 ; non-zero digit seen?
	tst.w   R8
	jnz     DigitShow
	cmp.w   #2, R14                 ; blank leading zeros, keep "0.x"
	jlo     DigitShow
	mov.w   #CHAR_SPACE, R11
DigitShow
	call    #SegChar_sr
	incd.w  R13
	dec.w   R14
	jge     DigitLoop
	bis.b   #SEGDP, &LCDM16         ; decimal point after position 1
	pop.w   R8
	ret

; SegChar_sr: R11 = CHAR index, R14 = position (0 = rightmost .. 5)
; Keeps R12-R15.
SegChar_sr:
	push.w  R12
	push.w  R15
	rla.w   R11
	mov.w   CHAR(R11), R11          ; segment pattern
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
