import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Html, Instance, Instances, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { Patient } from "../types";
import { DISTRICTS, MAP, placePatient, STATUS, toWorld } from "../city";

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
// Terrain — two landmasses split by Victoria Harbour, plus the southern hills.
// -----------------------------------------------------------------------------
const LAND_COLOR = "#dee4ea";
const HILL_COLOR = "#cdd6cf";
const WATER_COLOR = "#a7cfd2";
const BASE_COLOR = "#c6ccd4";

// Coastlines traced from the printed map, in normalized (nx, ny) map coords.
// Kowloon is the northern mass; Hong Kong Island the southern one. The gap
// between their facing coasts is Victoria Harbour — the water "running through".
const KOWLOON: [number, number][] = [
  [0.0, 0.0], [1.0, 0.0], [1.0, 0.4],
  [0.9, 0.4], [0.82, 0.44], [0.74, 0.4], [0.66, 0.34], [0.6, 0.33],
  [0.56, 0.4], [0.5, 0.45], [0.44, 0.5], [0.39, 0.55], // Tsim Sha Tsui tip
  [0.35, 0.52], [0.31, 0.45], [0.26, 0.41], [0.2, 0.4], [0.16, 0.43],
  [0.14, 0.36], [0.1, 0.3], [0.06, 0.22], [0.07, 0.12], [0.02, 0.07], [0.0, 0.05],
];

const ISLAND: [number, number][] = [
  [0.0, 0.66], [0.07, 0.61], [0.14, 0.585], [0.22, 0.585], [0.3, 0.59],
  [0.37, 0.605], [0.44, 0.59], [0.52, 0.59], [0.57, 0.605], // Causeway Bay shelter
  [0.64, 0.57], [0.72, 0.53], [0.82, 0.49], [0.9, 0.5], [1.0, 0.55],
  [1.0, 1.0], [0.0, 1.0],
];

// Small peaks. The island's hilly spine sits along the very bottom edge; a few
// modest hills rise behind north-east Kowloon (top right). Nothing in the middle,
// where the urban districts are.
const HILLS: [number, number, number, number][] = [
  // nx, ny, radius, height
  // Bottom edge — the island's peaks (small)
  [0.2, 0.95, 1.1, 0.9], [0.35, 0.97, 1.2, 1.0], [0.5, 0.96, 1.0, 0.85],
  [0.64, 0.97, 1.1, 0.95], [0.78, 0.95, 1.2, 1.0], [0.9, 0.93, 1.0, 0.8],
  // Top right — a small amount behind north-east Kowloon
  [0.84, 0.09, 1.2, 1.0], [0.93, 0.15, 1.0, 0.85], [0.9, 0.04, 0.9, 0.7],
];

function landGeometry(points: [number, number][]) {
  const shape = new THREE.Shape();
  points.forEach(([nx, ny], i) => {
    const { x, z } = toWorld(nx, ny);
    // rotation-x = -PI/2 maps shape (sx, sy) -> world (sx, 0, -sy); we want world z, so sy = -z.
    if (i === 0) shape.moveTo(x, -z);
    else shape.lineTo(x, -z);
  });
  shape.closePath();
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: LAND_TOP,
    bevelEnabled: true,
    bevelThickness: 0.08,
    bevelSize: 0.06,
    bevelSegments: 1,
  });
  return geo;
}

function Terrain() {
  const kowloon = useMemo(() => landGeometry(KOWLOON), []);
  const island = useMemo(() => landGeometry(ISLAND), []);

  // Kai Tak runway — a thin spit reaching into the eastern harbour.
  const runway = useMemo(() => {
    const a = toWorld(0.6, 0.29);
    const b = toWorld(0.81, 0.44);
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const len = Math.hypot(dx, dz);
    return {
      pos: [(a.x + b.x) / 2, LAND_TOP - 0.06, (a.z + b.z) / 2] as [number, number, number],
      rotY: -Math.atan2(dz, dx),
      len,
    };
  }, []);

  return (
    <group>
      {/* Model base tray — gives the rectangle a physical edge */}
      <mesh position={[0, -0.18, 0]} receiveShadow>
        <boxGeometry args={[MAP.w + 1.4, 0.5, MAP.d + 1.4]} />
        <meshStandardMaterial color={BASE_COLOR} roughness={0.9} />
      </mesh>

      {/* Harbour water — a rectangle the exact size of the map */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.12, 0]} receiveShadow>
        <planeGeometry args={[MAP.w, MAP.d]} />
        <meshStandardMaterial color={WATER_COLOR} roughness={0.3} metalness={0.1} />
      </mesh>

      {/* Landmasses with real coastlines */}
      <mesh geometry={kowloon} rotation-x={-Math.PI / 2} castShadow receiveShadow>
        <meshStandardMaterial color={LAND_COLOR} roughness={0.92} />
      </mesh>
      <mesh geometry={island} rotation-x={-Math.PI / 2} castShadow receiveShadow>
        <meshStandardMaterial color={LAND_COLOR} roughness={0.92} />
      </mesh>

      {/* Kai Tak runway */}
      <mesh position={runway.pos} rotation-y={runway.rotY} castShadow receiveShadow>
        <boxGeometry args={[runway.len, 0.3, 0.7]} />
        <meshStandardMaterial color={LAND_COLOR} roughness={0.92} />
      </mesh>

      {/* Topographic hills */}
      {HILLS.map(([nx, ny, r, h], i) => {
        const { x, z } = toWorld(nx, ny);
        return (
          <mesh key={i} position={[x, LAND_TOP - 0.05 + h / 2, z]} castShadow receiveShadow>
            <coneGeometry args={[r, h, 20]} />
            <meshStandardMaterial color={HILL_COLOR} roughness={1} />
          </mesh>
        );
      })}
    </group>
  );
}

// -----------------------------------------------------------------------------
// Buildings — instanced boxes clustered around each district core.
// -----------------------------------------------------------------------------
interface Building {
  position: [number, number, number];
  scale: [number, number, number];
  color: THREE.Color;
}

function useBuildings(): Building[] {
  return useMemo(() => {
    const out: Building[] = [];
    const base = new THREE.Color("#c3d0df");
    let seed = 7;
    const rand = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    for (const d of Object.values(DISTRICTS)) {
      if (d.side === "hills") continue; // hill districts stay green — no towers on mountains
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
      <meshStandardMaterial roughness={0.8} metalness={0.04} />
      {buildings.map((b, i) => (
        <Instance key={i} position={b.position} scale={b.scale} color={b.color} />
      ))}
    </Instances>
  );
}

// -----------------------------------------------------------------------------
// Patient marker — beam + status-shaped cap + glow halo. Urgent pulses.
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
  onSelect: (id: number) => void;
  onHover: (p: Patient | null) => void;
}

function Scene({ patients, selectedId, statusFilter, paused, onSelect, onHover }: SceneProps) {
  const reduced = usePrefersReducedMotion();
  const glow = useGlowTexture();
  const controls = useRef<any>(null);

  const placed = useMemo(() => patients.map(placePatient), [patients]);

  const target = useMemo(() => {
    const sel = placed.find((p) => p.patient.id === selectedId);
    return sel ? new THREE.Vector3(sel.x, sel.y + LAND_TOP + 1, sel.z) : null;
  }, [placed, selectedId]);

  return (
    <>
      <color attach="background" args={["#eef3f7"]} />
      <fog attach="fog" args={["#e7eef3", 34, 74]} />

      <hemisphereLight args={["#ffffff", "#aebccb", 0.9]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[14, 22, 12]}
        intensity={1.15}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-26}
        shadow-camera-right={26}
        shadow-camera-top={26}
        shadow-camera-bottom={-26}
      />

      <Terrain />
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
        position={[0, LAND_TOP + 0.02, 0]}
        scale={MAP.w + 6}
        far={14}
        blur={2.8}
        opacity={0.3}
        color="#46586d"
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
// Public component — the canvas + an in-stage hover tooltip overlay.
// -----------------------------------------------------------------------------
interface CityTwinProps {
  patients: Patient[];
  selectedId: number | null;
  statusFilter: Set<string> | null;
  onSelect: (id: number) => void;
}

export function CityTwin({ patients, selectedId, statusFilter, onSelect }: CityTwinProps) {
  const [hovered, setHovered] = useState<Patient | null>(null);

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: [0, 21, 28], fov: 40 }}
      gl={{ antialias: true }}
      onPointerMissed={() => setHovered(null)}
    >
      <Scene
        patients={patients}
        selectedId={selectedId}
        statusFilter={statusFilter}
        paused={hovered !== null}
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
