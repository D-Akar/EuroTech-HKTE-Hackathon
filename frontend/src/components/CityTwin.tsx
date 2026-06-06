import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { GoogleCityTwin } from "./GoogleCityTwin";
import {
  ContactShadows,
  Html,
  Instance,
  Instances,
  OrbitControls,
  useTexture,
} from "@react-three/drei";
import * as THREE from "three";
import type { Patient } from "../types";
import { DISTRICTS, MAP, placePatient, STATUS } from "../city";

// Height of the land slabs above the harbour; everything sits on top of this.
const LAND_TOP = 0.42;

// -----------------------------------------------------------------------------
// Reduced-motion: the living city holds still, urgency stays legible by shape.
// -----------------------------------------------------------------------------
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

// A soft radial glow texture, shared by every marker's halo sprite.
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
// Ground - real Hong Kong satellite imagery (Esri World Imagery) draped on the
// model tile. The harbour, coastlines and green hills all come from the photo;
// the 3D massing model and patient markers sit on top, like a physical city model.
// -----------------------------------------------------------------------------
const SAT_URL = "/hk-satellite.jpg";
const BASE_COLOR = "#161d29"; // deep tray beneath the floating satellite tile

function SatelliteGround() {
  const tex = useTexture(SAT_URL);
  useMemo(() => {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    tex.needsUpdate = true;
  }, [tex]);

  return (
    <group>
      {/* Deep base tray - gives the floating tile a physical, model-like edge */}
      <mesh position={[0, LAND_TOP - 0.3, 0]} receiveShadow>
        <boxGeometry args={[MAP.w + 0.7, 0.6, MAP.d + 0.7]} />
        <meshStandardMaterial color={BASE_COLOR} roughness={0.85} metalness={0.15} />
      </mesh>

      {/* Hong Kong from above - Victoria Harbour runs across the middle, Kowloon
          to the north, Hong Kong Island and the Peak's green hills to the south. */}
      <mesh rotation-x={-Math.PI / 2} position={[0, LAND_TOP, 0]} receiveShadow>
        <planeGeometry args={[MAP.w, MAP.d]} />
        <meshBasicMaterial map={tex} toneMapped={false} />
      </mesh>
    </group>
  );
}

// Plain gray ground - the "no satellite" fallback. Same floating model tray, but
// a neutral matte surface instead of the satellite photo, so the city reads as a
// clean schematic when the photoreal tiles are unavailable.
const PLAIN_GROUND = "#c5cad2";
const PLAIN_BG = "#dde1e7";
const PLAIN_BASE = "#aab1bb"; // neutral tray edge for the schematic twin - no black frame

function PlainGround() {
  return (
    <group>
      {/* Shallow base tray - same physical edge, but neutral gray so the tile reads
          as a clean schematic with no dark border. */}
      <mesh position={[0, LAND_TOP - 0.3, 0]}>
        <boxGeometry args={[MAP.w + 0.7, 0.6, MAP.d + 0.7]} />
        <meshStandardMaterial color={PLAIN_BASE} roughness={0.9} metalness={0} />
      </mesh>

      {/* Flat neutral land tile - no imagery. Does NOT receive the directional
          shadow map (that bands badly on a flat matte surface); building grounding
          comes from ContactShadows, exactly like the satellite tile. */}
      <mesh rotation-x={-Math.PI / 2} position={[0, LAND_TOP, 0]}>
        <planeGeometry args={[MAP.w, MAP.d]} />
        <meshStandardMaterial color={PLAIN_GROUND} roughness={0.95} metalness={0} />
      </mesh>
    </group>
  );
}

// -----------------------------------------------------------------------------
// Buildings - instanced boxes clustered around each district core.
// -----------------------------------------------------------------------------
interface Building {
  position: [number, number, number];
  scale: [number, number, number];
  color: THREE.Color;
}

function useBuildings(): Building[] {
  return useMemo(() => {
    const out: Building[] = [];
    const base = new THREE.Color("#eef2f7");
    let seed = 7;
    const rand = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    for (const d of Object.values(DISTRICTS)) {
      if (d.side === "hills") continue; // hill districts stay green - no towers on mountains
      const count = Math.round(6 + d.density * 12); // density drives how many towers
      const spread = 1.2 + d.density * 0.5;
      for (let i = 0; i < count; i++) {
        const a = rand() * Math.PI * 2;
        const r = Math.sqrt(rand()) * spread;
        const w = 0.28 + rand() * 0.34;
        // height drives how tall, independently of count, for an HK-shaped skyline
        const h = (0.5 + rand() * 2.6) * (0.4 + d.height) + d.y * 0.4;
        const col = base.clone();
        col.offsetHSL((rand() - 0.5) * 0.04, (rand() - 0.5) * 0.05, (rand() - 0.5) * 0.08);
        out.push({
          position: [d.x + Math.cos(a) * r, d.y + LAND_TOP + h / 2, d.z + Math.sin(a) * r],
          scale: [w, h, w * (0.8 + rand() * 0.5)],
          color: col,
        });
      }
    }
    return out;
  }, []);
}

function Buildings() {
  const buildings = useBuildings();
  return (
    <Instances limit={buildings.length} castShadow receiveShadow>
      <boxGeometry />
      <meshStandardMaterial roughness={0.52} metalness={0.16} />
      {buildings.map((b, i) => (
        <Instance key={i} position={b.position} scale={b.scale} color={b.color} />
      ))}
    </Instances>
  );
}

// -----------------------------------------------------------------------------
// Patient marker - beam + status-shaped cap + glow halo. Urgent pulses.
// -----------------------------------------------------------------------------
interface MarkerProps {
  placed: ReturnType<typeof placePatient>;
  selected: boolean;
  dimmed: boolean;
  reduced: boolean;
  glow: THREE.Texture;
  onSelect: (id: number) => void;
  onHover: (p: Patient | null) => void;
}

function PatientMarker({ placed, selected, dimmed, reduced, glow, onSelect, onHover }: MarkerProps) {
  const { patient, x, y, z } = placed;
  const meta = STATUS[patient.status];
  const isUrgent = patient.status === "urgent";
  const isAttention = patient.status === "attention";

  const beamH = isUrgent ? 1.9 : isAttention ? 1.2 : 0.85;
  const capY = beamH + 0.12;

  const pulseRef = useRef<THREE.Group>(null);
  const beamRef = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    if (reduced) return;
    const t = clock.getElapsedTime();
    if (pulseRef.current && (isUrgent || selected)) {
      const speed = isUrgent ? 3.2 : 2;
      const s = 1 + Math.sin(t * speed + patient.id) * (isUrgent ? 0.18 : 0.1);
      pulseRef.current.scale.setScalar(s);
    }
    if (beamRef.current && isUrgent) {
      const m = beamRef.current.material as THREE.MeshBasicMaterial;
      m.opacity = 0.4 + (Math.sin(t * 3.2 + patient.id) * 0.5 + 0.5) * 0.4;
    }
  });

  const opacity = dimmed ? 0.25 : 1;
  const color = meta.color;

  return (
    <group
      position={[x, y + LAND_TOP, z]}
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
      {/* Invisible hit cylinder for a comfortable click target */}
      <mesh position={[0, beamH / 2 + 0.1, 0]} visible={false}>
        <cylinderGeometry args={[0.4, 0.4, beamH + 0.6, 6]} />
        <meshBasicMaterial />
      </mesh>

      {/* Beam of light */}
      <mesh ref={beamRef} position={[0, beamH / 2 + 0.1, 0]}>
        <cylinderGeometry args={[0.05, 0.07, beamH, 10]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={(isUrgent ? 0.65 : 0.5) * opacity}
          depthWrite={false}
        />
      </mesh>

      {/* Ground ring footprint */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.04, 0]}>
        <ringGeometry args={[0.22, 0.3, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.5 * opacity} depthWrite={false} />
      </mesh>

      {/* Status cap (shape encodes status, not just color) */}
      <group ref={pulseRef} position={[0, capY, 0]}>
        {patient.status === "stable" && (
          <mesh>
            <sphereGeometry args={[0.17, 18, 18]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={0.6}
              transparent
              opacity={opacity}
            />
          </mesh>
        )}
        {patient.status === "attention" && (
          <mesh rotation-x={Math.PI / 2}>
            <torusGeometry args={[0.18, 0.055, 12, 28]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={0.6}
              transparent
              opacity={opacity}
            />
          </mesh>
        )}
        {patient.status === "urgent" && (
          <mesh>
            <octahedronGeometry args={[0.24]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={0.85}
              transparent
              opacity={opacity}
            />
          </mesh>
        )}

        {/* Glow halo */}
        <sprite scale={isUrgent ? 1.6 : selected ? 1.2 : 0.9}>
          <spriteMaterial
            map={glow}
            color={color}
            transparent
            opacity={(isUrgent ? 0.55 : 0.4) * opacity}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </sprite>
      </group>

      {/* Selection label */}
      {selected && (
        <Html position={[0, capY + 0.5, 0]} center distanceFactor={14} zIndexRange={[20, 0]}>
          <div className="marker-tip">
            {patient.name}
            <div className="tip-status">{meta.label}</div>
          </div>
        </Html>
      )}
    </group>
  );
}

// -----------------------------------------------------------------------------
// Camera that eases toward the selected patient.
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
    controls.current.target.lerp(target, 0.08);
    desired.current.set(target.x + 8, target.y + 9, target.z + 12);
    camera.position.lerp(desired.current, 0.05);
    controls.current.update();
  });
  return null;
}

// -----------------------------------------------------------------------------
// Scene
// -----------------------------------------------------------------------------
interface SceneProps {
  patients: Patient[];
  selectedId: number | null;
  statusFilter: Set<string> | null;
  paused: boolean;
  ground: "satellite" | "plain";
  onSelect: (id: number) => void;
  onHover: (p: Patient | null) => void;
}

function Scene({ patients, selectedId, statusFilter, paused, ground, onSelect, onHover }: SceneProps) {
  const reduced = usePrefersReducedMotion();
  const glow = useGlowTexture();
  const controls = useRef<any>(null);

  const placed = useMemo(() => patients.map(placePatient), [patients]);

  const target = useMemo(() => {
    const sel = placed.find((p) => p.patient.id === selectedId);
    return sel ? new THREE.Vector3(sel.x, sel.y + LAND_TOP + 1, sel.z) : null;
  }, [placed, selectedId]);

  const bg = ground === "plain" ? PLAIN_BG : "#e6eef6";

  return (
    <>
      <color attach="background" args={[bg]} />
      <fog attach="fog" args={[bg, 42, 92]} />

      <hemisphereLight args={["#ffffff", "#9fb0c2", 0.75]} />
      <ambientLight intensity={0.4} />
      <directionalLight
        position={[14, 24, 12]}
        intensity={1.0}
        color="#fff3e2"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-26}
        shadow-camera-right={26}
        shadow-camera-top={26}
        shadow-camera-bottom={-26}
        shadow-bias={-0.0004}
        shadow-normalBias={0.04}
      />

      <Suspense fallback={null}>
        {ground === "plain" ? <PlainGround /> : <SatelliteGround />}
      </Suspense>
      <Buildings />

      {placed.map((p) => {
        const dimmed = statusFilter ? !statusFilter.has(p.patient.status) : false;
        return (
          <PatientMarker
            key={p.patient.id}
            placed={p}
            selected={p.patient.id === selectedId}
            dimmed={dimmed}
            reduced={reduced}
            glow={glow}
            onSelect={onSelect}
            onHover={onHover}
          />
        );
      })}

      <ContactShadows
        position={[0, LAND_TOP + 0.015, 0]}
        scale={MAP.w + 6}
        far={14}
        blur={2.6}
        opacity={0.4}
        color="#0e1622"
      />

      <OrbitControls
        ref={controls}
        enablePan={false}
        minDistance={10}
        maxDistance={58}
        minPolarAngle={0.15}
        maxPolarAngle={Math.PI / 2.15}
        autoRotate={!reduced && selectedId === null && !paused}
        autoRotateSpeed={0.175}
        enableDamping
        dampingFactor={0.08}
        target={[0, 0, 0]}
      />
      <CameraRig target={target} controls={controls} />
    </>
  );
}

// -----------------------------------------------------------------------------
// Public component - the canvas + an in-stage hover tooltip overlay.
// -----------------------------------------------------------------------------
interface CityTwinProps {
  patients: Patient[];
  selectedId: number | null;
  statusFilter: Set<string> | null;
  onSelect: (id: number) => void;
}

// Public entry point. When a Google Maps API key is present we render the
// photorealistic 3D Tiles globe of Hong Kong; otherwise we fall back to the
// stylized gray schematic twin (no satellite imagery). The error boundary
// guarantees the stage still shows the city even if the tiles fail to load
// (bad key, Map Tiles API not enabled, offline), instead of blanking the stage.
const GOOGLE_MAPS_API_KEY = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? "").trim();

class TilesErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("Photorealistic 3D tiles failed - falling back to the gray schematic twin.", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function CityTwin(props: CityTwinProps) {
  // Flips to the gray schematic twin if the photoreal tiles fail at runtime (bad
  // key, Map Tiles API not enabled, offline) - a 403 is an async fetch error the
  // error boundary can't see, so GoogleCityTwin reports it via onError.
  const [tilesFailed, setTilesFailed] = useState(false);
  const handleTilesError = useCallback(() => setTilesFailed(true), []);

  if (!GOOGLE_MAPS_API_KEY || tilesFailed) {
    return <StylizedCityTwin {...props} ground="plain" />;
  }
  return (
    <TilesErrorBoundary fallback={<StylizedCityTwin {...props} ground="plain" />}>
      <GoogleCityTwin {...props} apiKey={GOOGLE_MAPS_API_KEY} onError={handleTilesError} />
    </TilesErrorBoundary>
  );
}

function StylizedCityTwin({
  patients,
  selectedId,
  statusFilter,
  onSelect,
  ground,
}: CityTwinProps & { ground: "satellite" | "plain" }) {
  const [hovered, setHovered] = useState<Patient | null>(null);

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: [0, 15, 20], fov: 40 }}
      gl={{ antialias: true }}
      onPointerMissed={() => setHovered(null)}
    >
      <Scene
        patients={patients}
        selectedId={selectedId}
        statusFilter={statusFilter}
        paused={hovered !== null}
        ground={ground}
        onSelect={onSelect}
        onHover={setHovered}
      />
      {hovered && hovered.id !== selectedId && <HoverTip patient={hovered} />}
    </Canvas>
  );
}

// Hover tooltip rendered in-scene at the hovered patient's position.
function HoverTip({ patient }: { patient: Patient }) {
  const placed = useMemo(() => placePatient(patient), [patient]);
  const meta = STATUS[patient.status];
  const beamH = patient.status === "urgent" ? 1.9 : patient.status === "attention" ? 1.2 : 0.85;
  return (
    <Html
      position={[placed.x, placed.y + LAND_TOP + beamH + 0.35, placed.z]}
      center
      distanceFactor={16}
    >
      <div className="marker-tip">
        {patient.name}
        <div className="tip-status">
          {meta.glyph} {meta.label} · {patient.district}
        </div>
      </div>
    </Html>
  );
}
