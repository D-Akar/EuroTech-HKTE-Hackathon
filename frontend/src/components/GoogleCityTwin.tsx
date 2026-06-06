import { Suspense, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";
import {
  TilesRenderer,
  TilesPlugin,
  TilesAttributionOverlay,
  TilesRendererContext,
} from "3d-tiles-renderer/r3f";
import {
  GoogleCloudAuthPlugin,
  GLTFExtensionsPlugin,
  TileCompressionPlugin,
  TilesFadePlugin,
  ReorientationPlugin,
} from "3d-tiles-renderer/plugins";
import type { Patient } from "../types";
import { HK_CENTER, patientLatLon, STATUS } from "../city";

// Photorealistic Hong Kong: Google's 3D Tiles, reoriented so Victoria Harbour
// sits at the world origin (+Y up). Patient markers are placed in metres on the
// local tangent plane, floating above the real buildings like care pins.

const EARTH_R = 6378137;
const DEG = Math.PI / 2 / 90;

// Stem heights (metres) — the placemark floats this high so the pin head clears
// the skyline, kept under Hong Kong's tallest towers so pins read as markers.
const BEAM_H: Record<string, number> = { urgent: 330, attention: 280, stable: 220 };

// Pin-head bulb radius per status (metres). The teardrop = bulb + downward cone.
const BULB_R: Record<string, number> = { urgent: 50, attention: 42, stable: 36 };

// Distance-responsive scaling: markers are sized in metres, so they shrink to
// dots when the camera pulls back. We scale each pin up with camera distance so
// it keeps a roughly constant on-screen size — like Google Earth placemarks —
// clamped so close-ups stay natural and far pins stay legible.
const SCALE_REF = 6000;
const SCALE_MIN = 1;
const SCALE_MAX = 3.4;

// ReorientationPlugin centres this lat/lon at the origin with +X west, +Z north.
function toScene(lat: number, lon: number): THREE.Vector3 {
  const north = (lat - HK_CENTER.lat) * DEG * EARTH_R;
  const east = (lon - HK_CENTER.lon) * DEG * EARTH_R * Math.cos(HK_CENTER.lat * DEG);
  return new THREE.Vector3(-east, 0, north);
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

function useGlowTexture() {
  return useMemo(() => {
    const size = 128;
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const ctx = c.getContext("2d")!;
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.25, "rgba(255,255,255,0.85)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, []);
}

// -----------------------------------------------------------------------------
// Google Photorealistic 3D Tiles of Hong Kong.
// -----------------------------------------------------------------------------
// Listens for the renderer's root-tileset failure. A `load-error` with
// `tile === null` means the whole Google dataset is unreachable — an invalid or
// unauthorized key, the Map Tiles API not enabled on the project, or offline —
// so we surface it to the parent, which swaps to the stylized satellite twin.
// Per-tile errors (tile !== null) are transient and ignored.
function TilesErrorListener({ onError }: { onError: () => void }) {
  const tiles = useContext(TilesRendererContext);
  useEffect(() => {
    if (!tiles) return;
    const onLoadError = (e: { tile: unknown }) => {
      if (e.tile === null) onError();
    };
    tiles.addEventListener("load-error", onLoadError);
    return () => tiles.removeEventListener("load-error", onLoadError);
  }, [tiles, onError]);
  return null;
}

function HongKongTiles({ apiKey, onError }: { apiKey: string; onError: () => void }) {
  const dracoLoader = useMemo(() => {
    const d = new DRACOLoader();
    d.setDecoderPath("/draco/");
    return d;
  }, []);
  useEffect(() => () => void dracoLoader.dispose(), [dracoLoader]);

  return (
    <TilesRenderer>
      <TilesPlugin plugin={GoogleCloudAuthPlugin} args={[{ apiToken: apiKey, autoRefreshToken: true }]} />
      <TilesPlugin plugin={GLTFExtensionsPlugin} args={[{ dracoLoader }]} />
      <TilesPlugin plugin={TileCompressionPlugin} />
      <TilesPlugin plugin={TilesFadePlugin} />
      <TilesPlugin
        plugin={ReorientationPlugin}
        args={[{ lat: HK_CENTER.lat * DEG, lon: HK_CENTER.lon * DEG, height: 0 }]}
      />
      <TilesAttributionOverlay />
      <TilesErrorListener onError={onError} />
    </TilesRenderer>
  );
}

// -----------------------------------------------------------------------------
// Patient marker — beam + status cap + glow halo, sized in metres.
// -----------------------------------------------------------------------------
interface MarkerProps {
  patient: Patient;
  pos: THREE.Vector3;
  selected: boolean;
  dimmed: boolean;
  reduced: boolean;
  glow: THREE.Texture;
  onSelect: (id: number) => void;
  onHover: (p: Patient | null) => void;
}

function GeoMarker({ patient, pos, selected, dimmed, reduced, glow, onSelect, onHover }: MarkerProps) {
  const meta = STATUS[patient.status];
  const isUrgent = patient.status === "urgent";
  const beamH = BEAM_H[patient.status] ?? BEAM_H.stable;
  const bulb = BULB_R[patient.status] ?? BULB_R.stable;
  const coneH = bulb * 1.7; // teardrop tail length
  const bulbY = coneH + bulb * 0.2; // bulb centre, sitting on the cone base
  const headTop = beamH + coneH + bulb * 2; // top of the pin (for tooltips)

  const pulseRef = useRef<THREE.Group>(null);
  const stemRef = useRef<THREE.Mesh>(null);
  const scaleRef = useRef<THREE.Group>(null);
  const haloRef = useRef<THREE.Sprite>(null);

  useFrame(({ clock, camera }) => {
    // Keep a near-constant on-screen size by scaling with camera distance.
    if (scaleRef.current) {
      const dist = camera.position.distanceTo(pos);
      const s = Math.min(SCALE_MAX, Math.max(SCALE_MIN, dist / SCALE_REF));
      scaleRef.current.scale.setScalar(s);
    }
    if (reduced) return;
    const t = clock.getElapsedTime();
    if (pulseRef.current && (isUrgent || selected)) {
      const speed = isUrgent ? 3.2 : 2;
      const s = 1 + Math.sin(t * speed + patient.id) * (isUrgent ? 0.16 : 0.09);
      pulseRef.current.scale.setScalar(s);
    }
    if (stemRef.current && isUrgent) {
      const m = stemRef.current.material as THREE.MeshBasicMaterial;
      m.opacity = 0.3 + (Math.sin(t * 3.2 + patient.id) * 0.5 + 0.5) * 0.35;
    }
    // Urgent halo breathes for an unmissable, high-contrast beacon.
    if (haloRef.current && isUrgent) {
      const m = haloRef.current.material as THREE.SpriteMaterial;
      m.opacity = (0.5 + (Math.sin(t * 3.2 + patient.id) * 0.5 + 0.5) * 0.42) * opacity;
    }
  });

  const opacity = dimmed ? 0.18 : 1;
  const color = meta.color;
  const emissive = isUrgent ? 2.6 : 1.15;

  return (
    <group
      position={pos}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(patient.id);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        onHover(patient);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        onHover(null);
        document.body.style.cursor = "auto";
      }}
    >
      <group ref={scaleRef}>
        {/* Comfortable click target spanning stem + head */}
        <mesh position={[0, (beamH + coneH) / 2, 0]} visible={false}>
          <cylinderGeometry args={[bulb * 1.6, bulb * 1.6, beamH + coneH + bulb * 3, 6]} />
          <meshBasicMaterial />
        </mesh>

        {/* Ground anchor — ring + dot where the pin "lands" on the city */}
        <mesh rotation-x={-Math.PI / 2} position={[0, 4, 0]}>
          <ringGeometry args={[bulb * 1.5, bulb * 2.1, 44]} />
          <meshBasicMaterial color={color} transparent opacity={0.5 * opacity} depthWrite={false} />
        </mesh>
        <mesh rotation-x={-Math.PI / 2} position={[0, 5, 0]}>
          <circleGeometry args={[bulb * 0.42, 24]} />
          <meshBasicMaterial color={color} transparent opacity={0.85 * opacity} depthWrite={false} />
        </mesh>

        {/* Thin stake lifting the placemark above the skyline */}
        <mesh ref={stemRef} position={[0, beamH / 2, 0]}>
          <cylinderGeometry args={[2.2, 3.4, beamH, 8]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={(isUrgent ? 0.55 : 0.38) * opacity}
            depthWrite={false}
          />
        </mesh>

        {/* Placemark head — teardrop pin (bulb + downward cone), tip at beamH */}
        <group ref={pulseRef} position={[0, beamH, 0]}>
          {/* Dark contrast shell (BackSide, scaled up) — a crisp outline so the
              bright pin pops against the busy photoreal city at any background.
              Urgent gets a thicker, near-black halo so red separates hard from
              terracotta rooftops and greenery. */}
          <mesh
            position={[0, coneH / 2, 0]}
            rotation-x={Math.PI}
            scale={isUrgent ? 1.34 : 1.2}
          >
            <coneGeometry args={[bulb * 0.82, coneH, 30]} />
            <meshBasicMaterial color="#02040a" side={THREE.BackSide} transparent opacity={opacity} />
          </mesh>
          <mesh position={[0, bulbY, 0]} scale={isUrgent ? 1.34 : 1.2}>
            <sphereGeometry args={[bulb, 30, 30]} />
            <meshBasicMaterial color="#02040a" side={THREE.BackSide} transparent opacity={opacity} />
          </mesh>

          {/* White rim between the dark shell and the colour — a crisp keyline
              that reads at distance, strongest on urgent pins. */}
          <mesh position={[0, bulbY, 0]} scale={isUrgent ? 1.16 : 1.08}>
            <sphereGeometry args={[bulb, 28, 28]} />
            <meshBasicMaterial
              color="#ffffff"
              side={THREE.BackSide}
              transparent
              opacity={(isUrgent ? 0.95 : 0.7) * opacity}
            />
          </mesh>

          {/* Cone tail, apex pointing down to the tip */}
          <mesh position={[0, coneH / 2, 0]} rotation-x={Math.PI}>
            <coneGeometry args={[bulb * 0.82, coneH, 30]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={emissive}
              toneMapped={false}
              transparent
              opacity={opacity}
              roughness={0.32}
              metalness={0.12}
            />
          </mesh>
          {/* Bulb */}
          <mesh position={[0, bulbY, 0]}>
            <sphereGeometry args={[bulb, 30, 30]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={emissive}
              toneMapped={false}
              transparent
              opacity={opacity}
              roughness={0.28}
              metalness={0.12}
            />
          </mesh>
          {/* Bright specular cap — a small highlight that gives the bulb a glossy,
              beacon-like read from any orbit angle (cheaper than a camera-facing hole) */}
          <mesh position={[0, bulbY + bulb * 0.34, 0]}>
            <sphereGeometry args={[bulb * 0.42, 18, 18]} />
            <meshStandardMaterial
              color="#ffffff"
              emissive="#ffffff"
              emissiveIntensity={0.6}
              toneMapped={false}
              transparent
              opacity={0.6 * opacity}
              roughness={0.2}
            />
          </mesh>

          {/* Glow halo behind the bulb */}
          <sprite
            ref={haloRef}
            position={[0, bulbY, 0]}
            scale={(isUrgent ? 19 : selected ? 14 : 11) * bulb}
          >
            <spriteMaterial
              map={glow}
              color={color}
              transparent
              opacity={(isUrgent ? 0.62 : 0.36) * opacity}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </sprite>
        </group>

        {selected && (
          <Html position={[0, headTop + 70, 0]} center distanceFactor={4200} zIndexRange={[20, 0]}>
            <div className="marker-tip">
              {patient.name}
              <div className="tip-status">{meta.label}</div>
            </div>
          </Html>
        )}
      </group>
    </group>
  );
}

// -----------------------------------------------------------------------------
// Camera that eases toward the selected patient (metre scale).
// -----------------------------------------------------------------------------
function CameraRig({
  target,
  controls,
}: {
  target: THREE.Vector3 | null;
  controls: React.RefObject<any>;
}) {
  const { camera } = useThree();
  const desired = useRef(new THREE.Vector3());
  useFrame(() => {
    if (!target || !controls.current) return;
    controls.current.target.lerp(target, 0.06);
    desired.current.set(target.x + 1400, target.y + 1600, target.z + 2200);
    camera.position.lerp(desired.current, 0.04);
    controls.current.update();
  });
  return null;
}

// -----------------------------------------------------------------------------
// Scene
// -----------------------------------------------------------------------------
interface SceneProps {
  apiKey: string;
  patients: Patient[];
  selectedId: number | null;
  statusFilter: Set<string> | null;
  paused: boolean;
  onSelect: (id: number) => void;
  onHover: (p: Patient | null) => void;
  onError: () => void;
}

function Scene({ apiKey, patients, selectedId, statusFilter, paused, onSelect, onHover, onError }: SceneProps) {
  const reduced = usePrefersReducedMotion();
  const glow = useGlowTexture();
  const controls = useRef<any>(null);

  const placed = useMemo(
    () =>
      patients.map((p) => {
        const { lat, lon } = patientLatLon(p);
        return { patient: p, pos: toScene(lat, lon) };
      }),
    [patients],
  );

  const target = useMemo(() => {
    const sel = placed.find((p) => p.patient.id === selectedId);
    return sel ? sel.pos.clone().setY(BEAM_H[sel.patient.status] ?? 340) : null;
  }, [placed, selectedId]);

  return (
    <>
      <color attach="background" args={["#bcd3e6"]} />
      <fog attach="fog" args={["#bcd3e6", 14000, 46000]} />

      <hemisphereLight args={["#ffffff", "#86929e", 0.7]} />
      <ambientLight intensity={1.25} />
      <directionalLight position={[6000, 12000, 4000]} intensity={1.4} color="#fff4e6" />

      <Suspense fallback={null}>
        <HongKongTiles apiKey={apiKey} onError={onError} />
      </Suspense>

      {placed.map((p) => {
        const dimmed = statusFilter ? !statusFilter.has(p.patient.status) : false;
        return (
          <GeoMarker
            key={p.patient.id}
            patient={p.patient}
            pos={p.pos}
            selected={p.patient.id === selectedId}
            dimmed={dimmed}
            reduced={reduced}
            glow={glow}
            onSelect={onSelect}
            onHover={onHover}
          />
        );
      })}

      <OrbitControls
        ref={controls}
        enablePan={false}
        minDistance={1500}
        maxDistance={32000}
        minPolarAngle={0.1}
        maxPolarAngle={Math.PI / 2.15}
        autoRotate={!reduced && selectedId === null && !paused}
        autoRotateSpeed={0.16}
        enableDamping
        dampingFactor={0.07}
        target={[0, 0, -1800]}
      />
      <CameraRig target={target} controls={controls} />
    </>
  );
}

// -----------------------------------------------------------------------------
// Public component
// -----------------------------------------------------------------------------
interface Props {
  apiKey: string;
  patients: Patient[];
  selectedId: number | null;
  statusFilter: Set<string> | null;
  onSelect: (id: number) => void;
  onError: () => void;
}

export function GoogleCityTwin({ apiKey, patients, selectedId, statusFilter, onSelect, onError }: Props) {
  const [hovered, setHovered] = useState<Patient | null>(null);

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 9000, 9500], near: 1, far: 220000, fov: 55 }}
      gl={{ antialias: true, logarithmicDepthBuffer: true }}
      onPointerMissed={() => setHovered(null)}
    >
      <Scene
        apiKey={apiKey}
        patients={patients}
        selectedId={selectedId}
        statusFilter={statusFilter}
        paused={hovered !== null}
        onSelect={onSelect}
        onHover={setHovered}
        onError={onError}
      />
      {hovered && hovered.id !== selectedId && <HoverTip patient={hovered} />}
    </Canvas>
  );
}

function HoverTip({ patient }: { patient: Patient }) {
  const pos = useMemo(() => {
    const { lat, lon } = patientLatLon(patient);
    return toScene(lat, lon);
  }, [patient]);
  const meta = STATUS[patient.status];
  const beamH = BEAM_H[patient.status] ?? BEAM_H.stable;
  const bulb = BULB_R[patient.status] ?? BULB_R.stable;
  const headTop = beamH + bulb * 1.7 + bulb * 2;
  return (
    <Html position={[pos.x, headTop + 60, pos.z]} center distanceFactor={4600}>
      <div className="marker-tip">
        {patient.name}
        <div className="tip-status">
          {meta.glyph} {meta.label} · {patient.district}
        </div>
      </div>
    </Html>
  );
}
