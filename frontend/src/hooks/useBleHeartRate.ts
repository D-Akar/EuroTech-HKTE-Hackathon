import { useCallback, useEffect, useRef, useState } from "react";

// Real-time heart rate straight from the watch over Bluetooth Low Energy, bypassing the
// Garmin cloud entirely. The watch must have "Broadcast Heart Rate" enabled, and the page
// must run in a secure context (https or localhost) in Chrome/Edge. Reads the standard
// BLE Heart Rate Service (0x180D) -> Heart Rate Measurement characteristic (0x2A37).
//
// Web Bluetooth types are not in the project's TS lib, so the BLE objects are typed loosely
// here on purpose; the parsing follows the GATT Heart Rate Measurement spec.

const HR_SERVICE = "heart_rate"; // 0x180D
const HR_MEASUREMENT = "heart_rate_measurement"; // 0x2A37

export type BleStatus = "unsupported" | "idle" | "connecting" | "connected" | "error";

export interface BleHeartRate {
  supported: boolean;
  status: BleStatus;
  bpm: number | null;
  at: string | null; // ISO timestamp of the most recent beat reading
  deviceName: string | null;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
}

// Heart Rate Measurement: byte 0 is flags; bit 0 selects uint8 (0) vs uint16 (1) for the value.
function parseHeartRate(value: DataView): number {
  const flags = value.getUint8(0);
  const is16 = (flags & 0x01) === 0x01;
  return is16 ? value.getUint16(1, true) : value.getUint8(1);
}

export function useBleHeartRate(): BleHeartRate {
  const supported =
    typeof navigator !== "undefined" && !!(navigator as unknown as { bluetooth?: unknown }).bluetooth;

  const [status, setStatus] = useState<BleStatus>(supported ? "idle" : "unsupported");
  const [bpm, setBpm] = useState<number | null>(null);
  const [at, setAt] = useState<string | null>(null);
  const [deviceName, setDeviceName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const deviceRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const charRef = useRef<any>(null);

  const onValue = useCallback((event: Event) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const target = event.target as any;
    const value: DataView | undefined = target?.value;
    if (value) {
      setBpm(parseHeartRate(value));
      setAt(new Date().toISOString());
    }
  }, []);

  const onDisconnected = useCallback(() => {
    setStatus("idle");
    setBpm(null);
  }, []);

  const cleanup = useCallback(() => {
    const ch = charRef.current;
    if (ch) {
      ch.removeEventListener("characteristicvaluechanged", onValue);
      try {
        ch.stopNotifications?.().catch(() => {});
      } catch {
        /* ignore */
      }
      charRef.current = null;
    }
    const dev = deviceRef.current;
    if (dev) {
      dev.removeEventListener?.("gattserverdisconnected", onDisconnected);
      if (dev.gatt?.connected) dev.gatt.disconnect();
    }
  }, [onValue, onDisconnected]);

  const connect = useCallback(async () => {
    if (!supported) {
      setStatus("unsupported");
      return;
    }
    setError(null);
    setStatus("connecting");
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bt = (navigator as unknown as { bluetooth: any }).bluetooth;
      const dev = await bt.requestDevice({
        filters: [{ services: [HR_SERVICE] }],
        optionalServices: [HR_SERVICE],
      });
      deviceRef.current = dev;
      setDeviceName(dev.name ?? "Watch");
      dev.addEventListener("gattserverdisconnected", onDisconnected);

      const server = await dev.gatt.connect();
      const service = await server.getPrimaryService(HR_SERVICE);
      const ch = await service.getCharacteristic(HR_MEASUREMENT);
      charRef.current = ch;
      ch.addEventListener("characteristicvaluechanged", onValue);
      await ch.startNotifications();
      setStatus("connected");
    } catch (err) {
      // The chooser being dismissed is a normal cancel, not an error state.
      if (err instanceof Error && err.name === "NotFoundError") {
        setStatus("idle");
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }, [supported, onValue, onDisconnected]);

  const disconnect = useCallback(() => {
    cleanup();
    deviceRef.current = null;
    setStatus(supported ? "idle" : "unsupported");
    setBpm(null);
    setAt(null);
    setDeviceName(null);
    setError(null);
  }, [cleanup, supported]);

  useEffect(() => () => cleanup(), [cleanup]);

  return { supported, status, bpm, at, deviceName, error, connect, disconnect };
}
