/*
 * HAL_MSP_EXP430FR6989_Crystalfontz128x128_ST7735.h
 *
 * Hardware layer for TI's Crystalfontz128x128_ST7735 grlib driver on the
 * MSP-EXP430FR6989 LaunchPad + BOOSTXL-EDUMKII (Educational BoosterPack MKII).
 * Same interface as TI's HAL_MSP_EXP432P401R_Crystalfontz128x128_ST7735.h.
 *
 *   LCD signal   BP pin   FR6989
 *   SPI CLK        7      P1.4 / UCB0CLK
 *   SPI MOSI      15      P1.6 / UCB0SIMO
 *   LCD RST       17      P9.4
 *   LCD CS        13      P2.5
 *   LCD RS (D/C)  31      P2.3
 *   (Same pins your Pong_Assembly project drives.)
 */
#ifndef HAL_MSP_EXP430FR6989_CRYSTALFONTZ128X128_ST7735_H_
#define HAL_MSP_EXP430FR6989_CRYSTALFONTZ128X128_ST7735_H_

#include <stdint.h>
#include "driverlib.h"

#include "bench_clock.h"                /* TI_C_Bench: BENCH_MHZ */
#define LCD_SYSTEM_CLOCK_SPEED  (BENCH_MHZ * 1000000UL)  /* SMCLK feeding eUSCI_B0 */
#define LCD_SPI_CLOCK_SPEED     (BENCH_MHZ * 1000000UL)  /* same as tft4: SPI = SMCLK */

#define LCD_SCK_PORT            GPIO_PORT_P1
#define LCD_SCK_PIN             GPIO_PIN4
#define LCD_SCK_PIN_FUNCTION    GPIO_PRIMARY_MODULE_FUNCTION
#define LCD_MOSI_PORT           GPIO_PORT_P1
#define LCD_MOSI_PIN            GPIO_PIN6
#define LCD_MOSI_PIN_FUNCTION   GPIO_PRIMARY_MODULE_FUNCTION
#define LCD_RST_PORT            GPIO_PORT_P9
#define LCD_RST_PIN             GPIO_PIN4
#define LCD_CS_PORT             GPIO_PORT_P2
#define LCD_CS_PIN              GPIO_PIN5
#define LCD_DC_PORT             GPIO_PORT_P2
#define LCD_DC_PIN              GPIO_PIN3

#define LCD_EUSCI_BASE          EUSCI_B0_BASE

extern void HAL_LCD_writeCommand(uint8_t command);
extern void HAL_LCD_writeData(uint8_t data);
extern void HAL_LCD_PortInit(void);
extern void HAL_LCD_SpiInit(void);
extern void HAL_LCD_delayMs(uint16_t ms);

/* Extra (not in TI's HAL): stream 8 pixels from a 1-bpp byte, MSB first.
 * '0' bits get 'ink', '1' bits get 'paper'. Used by the game's canvas. */
extern void HAL_LCD_writePixels8(uint8_t bits, uint16_t ink, uint16_t paper);

/* TI's driver calls HAL_LCD_delay(50/120/200/10) around reset and sleep-out;
 * the ST7735 needs those in milliseconds (120 ms after SLPOUT). */
#define HAL_LCD_delay(x)        HAL_LCD_delayMs(x)

#endif
