#ifndef __SERIAL_H
#define __SERIAL_H

#include "stm32f10x.h"

extern volatile uint8_t Serial_RxPacket[];
extern volatile uint8_t Serial_RxFlag;

void Serial_Init(void);
void Serial_SendByte(uint8_t Byte);
void Serial_SendArray(uint8_t *Array, uint16_t Length);
void Serial_SendString(char *String);
void Serial_SendNumber(uint32_t Number, uint8_t Length);
void Serial_Printf(char *format, ...);

void Serial_SendFrame(uint8_t byte0, uint8_t byte1, uint8_t byte2);
uint8_t Serial_GetRxFlag(void);

#endif
