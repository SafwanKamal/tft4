/*
 * HAL_MSP_EXP430FR6989_Crystalfontz128x128_ST7735.c - see the .h
 * Modeled on TI's HAL_MSP_EXP432P401R_Crystalfontz128x128_ST7735.c.
 */
#include "HAL_MSP_EXP430FR6989_Crystalfontz128x128_ST7735.h"
#include "grlib.h"

void HAL_LCD_PortInit(void)
{
    GPIO_setAsPeripheralModuleFunctionOutputPin(LCD_SCK_PORT, LCD_SCK_PIN, LCD_SCK_PIN_FUNCTION);
    GPIO_setAsPeripheralModuleFunctionOutputPin(LCD_MOSI_PORT, LCD_MOSI_PIN, LCD_MOSI_PIN_FUNCTION);
    GPIO_setOutputHighOnPin(LCD_RST_PORT, LCD_RST_PIN);
    GPIO_setAsOutputPin(LCD_RST_PORT, LCD_RST_PIN);
    GPIO_setOutputHighOnPin(LCD_DC_PORT, LCD_DC_PIN);
    GPIO_setAsOutputPin(LCD_DC_PORT, LCD_DC_PIN);
    GPIO_setOutputHighOnPin(LCD_CS_PORT, LCD_CS_PIN);
    GPIO_setAsOutputPin(LCD_CS_PORT, LCD_CS_PIN);
}

void HAL_LCD_SpiInit(void)
{
    EUSCI_B_SPI_initMasterParam param = {
        EUSCI_B_SPI_CLOCKSOURCE_SMCLK,
        LCD_SYSTEM_CLOCK_SPEED,
        LCD_SPI_CLOCK_SPEED,
        EUSCI_B_SPI_MSB_FIRST,
        EUSCI_B_SPI_PHASE_DATA_CAPTURED_ONFIRST_CHANGED_ON_NEXT,   /* SPI mode 0 */
        EUSCI_B_SPI_CLOCKPOLARITY_INACTIVITY_LOW,
        EUSCI_B_SPI_3PIN
    };
    EUSCI_B_SPI_initMaster(LCD_EUSCI_BASE, &param);
    EUSCI_B_SPI_enable(LCD_EUSCI_BASE);

    GPIO_setOutputLowOnPin(LCD_CS_PORT, LCD_CS_PIN);      /* only device on the bus */
    GPIO_setOutputHighOnPin(LCD_DC_PORT, LCD_DC_PIN);
}

void HAL_LCD_writeCommand(uint8_t command)
{
    while (UCB0STATW & UCBUSY) { }          /* finish any data byte first */
    P2OUT &= ~BIT3;                         /* D/C low = command          */
    UCB0TXBUF = command;
    while (UCB0STATW & UCBUSY) { }
    P2OUT |= BIT3;                          /* back to data               */
}

void HAL_LCD_writeData(uint8_t data)
{
    while (!(UCB0IFG & UCTXIFG)) { }        /* pipelined: wait for buffer, not bus */
    UCB0TXBUF = data;
}

void HAL_LCD_writePixels8(uint8_t bits, uint16_t ink, uint16_t paper)
{
    uint8_t m;
    for (m = 0x80; m; m >>= 1) {
        uint16_t c = (bits & m) ? paper : ink;
        while (!(UCB0IFG & UCTXIFG)) { }
        UCB0TXBUF = (uint8_t)(c >> 8);
        while (!(UCB0IFG & UCTXIFG)) { }
        UCB0TXBUF = (uint8_t)c;
    }
}

void HAL_LCD_delayMs(uint16_t ms)
{
    while (ms--) __delay_cycles(LCD_SYSTEM_CLOCK_SPEED / 1000);
}
