/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FTEC_REPORT_FIFO_H
#define FTEC_REPORT_FIFO_H

#include <linux/string.h>

#define FTEC_REPORT_BYTES 64
#define FTEC_REPORT_DEPTH 4

/* The caller serializes access and provides capacity for one output report. */
struct ftec_report_fifo {
	struct {
		u8 bytes[FTEC_REPORT_BYTES];
		size_t len;
	} packets[FTEC_REPORT_DEPTH];
	unsigned int head;
	unsigned int used;
};

static inline bool ftec_fifo_push(struct ftec_report_fifo *fifo,
				  const u8 *buf, size_t len)
{
	unsigned int tail;

	if (!len || len > FTEC_REPORT_BYTES || fifo->used == FTEC_REPORT_DEPTH)
		return false;

	tail = (fifo->head + fifo->used) % FTEC_REPORT_DEPTH;
	memcpy(fifo->packets[tail].bytes, buf, len);
	fifo->packets[tail].len = len;
	fifo->used++;
	return true;
}

static inline size_t ftec_fifo_pop(struct ftec_report_fifo *fifo, u8 *buf)
{
	size_t len;

	if (!fifo->used)
		return 0;

	len = fifo->packets[fifo->head].len;
	memcpy(buf, fifo->packets[fifo->head].bytes, len);
	fifo->head = (fifo->head + 1) % FTEC_REPORT_DEPTH;
	fifo->used--;
	return len;
}

#endif
