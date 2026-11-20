/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef uint8_t u8;
#include "ftec-report-fifo.h"

struct work_struct { bool pending; };
struct fake_hid { int dev; };
struct ftec_drv_data {
	struct fake_hid *hid;
	struct work_struct ff_work;
	bool ff_lock;
	struct ftec_report_fifo ff_fifo;
	u8 *ff_send;
	bool ff_stopping;
	unsigned long ff_accepted;
	unsigned long ff_overruns;
	unsigned long ff_errors;
};

static struct ftec_drv_data driver;
static u8 sent[32];
static unsigned int sent_count;
static bool send_fails;

#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define spin_lock_irqsave(lock, flags) do { (flags) = 0; assert(!*(lock)); *(lock) = true; } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(flags); assert(*(lock)); *(lock) = false; } while (0)
#define dev_warn_ratelimited(...) ((void)0)
#define hid_info(...) ((void)0)

static void schedule_work(struct work_struct *work)
{
	assert(driver.ff_lock && !driver.ff_stopping);
	work->pending = true;
}

static void cancel_work_sync(struct work_struct *work)
{
	assert(!driver.ff_lock && driver.ff_stopping);
	assert(!driver.ff_fifo.used);
	work->pending = false;
}

static int hid_hw_output_report(struct fake_hid *hid, u8 *buf, size_t len)
{
	assert(hid == driver.hid && !driver.ff_lock);
	assert(buf == driver.ff_send && len == FTEC_REPORT_BYTES);
	assert(buf[0] == 255);
	sent[sent_count++] = buf[1];
	return send_fails ? -EIO : (int)len;
}

#include "report-worker.inc"

static int submit(u8 sequence)
{
	u8 packet[FTEC_REPORT_BYTES] = {255, sequence};
	int ret = ftec_ff_submit(&driver, packet, sizeof(packet));
	packet[1] = 0; /* caller's buffer can be reused immediately */
	return ret;
}

static void run_worker(void)
{
	assert(driver.ff_work.pending);
	driver.ff_work.pending = false;
	ftec_ff_work(&driver.ff_work);
}

int main(void)
{
	static struct fake_hid hid;
	static u8 send_buffer[FTEC_REPORT_BYTES];
	driver.hid = &hid;
	driver.ff_send = send_buffer;
	assert(!ftec_fifo_push(&driver.ff_fifo, send_buffer, 0));
	assert(!ftec_fifo_push(&driver.ff_fifo, send_buffer, FTEC_REPORT_BYTES + 1));

	/* Overflow cannot evict an accepted packet. Replay through wraparound. */
	for (u8 i = 1; i <= FTEC_REPORT_DEPTH; i++)
		assert(submit(i) == FTEC_REPORT_BYTES);
	assert(submit(99) == -EBUSY && driver.ff_overruns == 1);
	assert(!sent_count && driver.ff_accepted == FTEC_REPORT_DEPTH);
	run_worker();
	for (u8 i = 1; i <= FTEC_REPORT_DEPTH; i++)
		assert(sent[i - 1] == i);

	assert(submit(101) == FTEC_REPORT_BYTES);
	send_fails = true;
	run_worker();
	assert(driver.ff_errors == 1 && sent[FTEC_REPORT_DEPTH] == 101);
	assert(submit(102) == FTEC_REPORT_BYTES);
	ftec_ff_stop(&driver);
	assert(!driver.ff_work.pending);
	assert(submit(103) == -ENODEV);
	assert(sent_count == FTEC_REPORT_DEPTH + 1);

	puts("Report-255 worker tests passed (simulated workqueue and USB).");
	return 0;
}
