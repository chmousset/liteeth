#!/usr/bin/env python3
from litex.gen import *

from litex.soc.interconnect import wishbone
from litex.soc.interconnect.stream_sim import *

from liteeth.common import *
from liteeth.core.mac import LiteEthMAC

from model import phy, mac


class WishboneMaster:
    def __init__(self, obj):
        self.obj = obj
        self.dat = 0

    def write(self, adr, dat):
        yield self.obj.cyc.eq(1)
        yield self.obj.stb.eq(1)
        yield self.obj.adr.eq(adr)
        yield self.obj.we.eq(1)
        yield self.obj.sel.eq(0xf)
        yield self.obj.dat_w.eq(dat)
        while (yield self.obj.ack) == 0:
            yield
        yield self.obj.cyc.eq(0)
        yield self.obj.stb.eq(0)
        yield

    def read(self, adr):
        yield self.obj.cyc.eq(1)
        yield self.obj.stb.eq(1)
        yield self.obj.adr.eq(adr)
        yield self.obj.we.eq(0)
        yield self.obj.sel.eq(0xf)
        yield self.obj.dat_w.eq(0)
        while (yield self.obj.ack) == 0:
            yield
        yield self.dat.eq(self.obj.dat_r)
        yield self.obj.cyc.eq(0)
        yield self.obj.stb.eq(0)
        yield


class SRAMReaderDriver:
    def __init__(self, obj):
        self.obj = obj

    def start(self, slot, length):
        yield self.obj._slot.storage.eq(slot)
        yield self.obj._length.storage.eq(length)
        yield self.obj._start.re.eq(1)
        yield
        yield self.obj._start.re.eq(0)
        yield

    def wait_done(self):
        while (yield self.obj.ev.done.pending) == 0:
            yield

    def clear_done(self):
        yield self.obj.ev.done.clear.eq(1)
        yield
        yield self.obj.ev.done.clear.eq(0)
        yield


class SRAMWriterDriver:
    def __init__(self, obj):
        self.obj = obj

    def wait_available(self):
        while (yield self.obj.ev.available.pending) == 0:
            yield

    def clear_available(self):
        yield self.obj.ev.available.clear.eq(1)
        yield
        yield self.obj.ev.available.clear.eq(0)
        yield


class TB(Module):
    def __init__(self):
        self.submodules.phy_model = phy.PHY(8, debug=True)
        self.submodules.mac_model = mac.MAC(self.phy_model, debug=True, loopback=True)
        self.submodules.ethmac = LiteEthMAC(phy=self.phy_model, dw=32, interface="wishbone", with_preamble_crc=True)


def main_generator(dut):
    wishbone_master = WishboneMaster(dut.ethmac.bus)
    sram_reader_driver = SRAMReaderDriver(dut.ethmac.interface.sram.reader)
    sram_writer_driver = SRAMWriterDriver(dut.ethmac.interface.sram.writer)

    sram_writer_slots_offset = [0x000, 0x200]
    sram_reader_slots_offset = [0x400, 0x600]

    length = 150+2

    tx_payload = [seed_to_data(i, True) % 0xFF for i in range(length)] + [0, 0, 0, 0]

    errors = 0

    while True:
        for i in range(20):
            yield
        for slot in range(2):
            print("slot {}: ".format(slot), end="")
            # fill tx memory
            for i in range(length//4+1):
                dat = int.from_bytes(tx_payload[4*i:4*(i+1)], "big")
                yield from wishbone_master.write(sram_reader_slots_offset[slot]+i, dat)


#            # send tx payload & wait
#            yield from sram_reader_driver.start(slot, length)
#            yield from sram_reader_driver.wait_done()
#            yield from sram_reader_driver.clear_done()
#
#            # wait rx
#            yield from sram_writer_driver.wait_available()
#            yield from sram_writer_driver.clear_available()
#
#            # get rx payload (loopback on PHY Model)
#            rx_payload = []
#            for i in range(length//4+1):
#                yield from wishbone_master.read(sram_writer_slots_offset[slot]+i)
#                dat = wishbone_master.dat
#                rx_payload += list(dat.to_bytes(4, byteorder='big'))
#
#            # check results
#            s, l, e = check(tx_payload[:length], rx_payload[:min(length, len(rx_payload))])
#            print("shift " + str(s) + " / length " + str(l) + " / errors " + str(e))

if __name__ == "__main__":
    tb = TB()
    generators = {
        "sys" :    main_generator(tb),
        "eth_tx": [tb.phy_model.phy_sink.generator(),
                   tb.phy_model.generator()],
        "eth_rx":  tb.phy_model.phy_source.generator()
    }
    clocks = {"sys":    10,
              "eth_rx": 10,
              "eth_tx": 10}
    run_simulation(tb, generators, clocks, vcd_name="sim.vcd")
