#include "stm32f10x.h"
#include "Relay.h"

#define RELAY_PORT				GPIOA
#define RELAY1_PIN				GPIO_Pin_3
#define RELAY2_PIN				GPIO_Pin_4
#define RELAY3_PIN				GPIO_Pin_5
#define RELAY_ALL_PINS			(RELAY1_PIN | RELAY2_PIN | RELAY3_PIN)

static uint8_t Relay_StateMask;

static void Relay_WritePin(uint16_t pin, uint8_t is_on)
{
	if (is_on)
	{
		GPIO_SetBits(RELAY_PORT, pin);
	}
	else
	{
		GPIO_ResetBits(RELAY_PORT, pin);
	}
}

void Relay_Init(void)
{
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
	
	GPIO_InitTypeDef GPIO_InitStructure;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin = RELAY_ALL_PINS;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(RELAY_PORT, &GPIO_InitStructure);
	
	GPIO_ResetBits(RELAY_PORT, RELAY_ALL_PINS);
	Relay_StateMask = 0x00;
}

void Relay_SetChannel(uint8_t channel, uint8_t is_on)
{
	uint16_t pin = 0;
	uint8_t bit = 0;
	
	if (channel == 1)
	{
		pin = RELAY1_PIN;
		bit = 0;
	}
	else if (channel == 2)
	{
		pin = RELAY2_PIN;
		bit = 1;
	}
	else if (channel == 3)
	{
		pin = RELAY3_PIN;
		bit = 2;
	}
	else
	{
		return;
	}
	
	Relay_WritePin(pin, is_on);
	
	if (is_on)
	{
		Relay_StateMask |= (1 << bit);
	}
	else
	{
		Relay_StateMask &= (uint8_t)~(1 << bit);
	}
}

void Relay_SetAll(uint8_t state_mask)
{
	Relay_SetChannel(1, (state_mask >> 0) & 0x01);
	Relay_SetChannel(2, (state_mask >> 1) & 0x01);
	Relay_SetChannel(3, (state_mask >> 2) & 0x01);
}

uint8_t Relay_GetStateMask(void)
{
	return Relay_StateMask & 0x07;
}
