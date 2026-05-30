#ifndef __RELAY_H
#define __RELAY_H

#include "stm32f10x.h"

void Relay_Init(void);
void Relay_SetChannel(uint8_t channel, uint8_t is_on);
void Relay_SetAll(uint8_t state_mask);
uint8_t Relay_GetStateMask(void);

#endif
