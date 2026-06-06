import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Html, Instance, Instances, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { Patient } from "../types";
import { DISTRICTS, placePatient, STATUS } from "../city";

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
const LAND_COLOR = "#dfe5ec";
const WATER_COLOR = "#9fcbcf";

function Terrain() {
  return (
    <group>
      {/* Sea */}
      <mesh rotation-x={-Math.PI / 2} position={[1, -0.12, -1]} receiveShadow>
        <planeGeometry args={[60, 60]} />
        <meshStandardMaterial color={WATER_COLOR} roughness={0.35} metalness={0.05} />
      </mesh>

      {/* Kowloon (north of the harbour) */}
      <mesh position={[-1.5, 0, -7.2]} receiveShadow>
        <boxGeometry args={[16, 0.35, 6.4]} />
        <meshStandardMaterial color={LAND_COLOR} roughness={0.95} />
      </mesh>

      {/* Hong Kong Island north shore + flats */}
      <mesh position={[1.5, 0, 1.2]} receiveShadow>
        <boxGeometry args={[20, 0.35, 4]} />
        <meshStandardMaterial color={LAND_COLOR} roughness={0.95} />
      </mesh>

      {/* Island mass extending south into the hills */}
      <mesh position={[0.5, 0, 6.4]} receiveShadow>
        <boxGeometry args={[18, 0.35, 7] } />
        <meshStandardMaterial color={LAND_COLOR} roughness={0.95} />
      </mesh>

      {/* The Peak — a soft hill rising over the island */}
      <mesh position={[DISTRICTS["The Peak"].x, 0.6, DISTRICTS["The Peak"].z]} receiveShadow castShadow>
        <coneGeometry args={[3.2, 2.6, 24]} />
        <meshStandardMaterial color="#cdd8d2" roughness={1} />
      </mesh>
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
      const count = Math.round(6 + d.density * 12);
      const spread = 1.7 + d.density * 0.6;
      for (let i = 0; i < count; i++) {
        const a = rand() * Math.PI * 2;
        const r = Math.sqrt(rand()) * spread;
        const w = 0.28 + rand() * 0.34;
        const h = (0.5 + rand() * 2.6) * (0.5 + d.density) + d.y * 0.4;
        const col = base.clone();
        col.offsetHSL((rand() - 0.5) * 0.04, (rand() - 0.5) * 0.05, (rand() - 0.5) * 0.08);
        out.push({
          position: [d.x + Math.cos(a) * r, d.y + h / 2 + 0.15, d.z + Math.sin(a) * r],
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
  const capY = y + 0.2 + beamH;

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
      position={[x, y, z]}
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
      <mesh position={[0, 0.2 + beamH / 2, 0]} visible={false}>
        <cylinderGeometry args={[0.4, 0.4, beamH + 0.6, 6]} />
        <meshBasicMaterial />
      </mesh>

      {/* Beam of light */}
      <mesh ref={beamRef} position={[0, 0.2 + beamH / 2, 0]}>
        <cylinderGeometry args={[0.05, 0.07, beamH, 10]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={(isUrgent ? 0.65 : 0.5) * opacity}
          depthWrite={false}
        />
      </mesh>

      {/* Ground ring footprint */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.22, 0]}>
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
    desired.current.set(target.x + 6, target.y + 7, target.z + 9);
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
  onSelect: (id: number) => void;
  onHover: (p: Patient | null) => void;
}

function Scene({ patients, selectedId, statusFilter, onSelect, onHover }: SceneProps) {
  const reduced = usePrefersReducedMotion();
  const glow = useGlowTexture();
  const controls = useRef<any>(null);

  const placed = useMemo(() => patients.map(placePatient), [patients]);

  const target = useMemo(() => {
    const sel = placed.find((p) => p.patient.id === selectedId);
    return sel ? new THREE.Vector3(sel.x, sel.y + 1, sel.z) : null;
  }, [placed, selectedId]);

  return (
    <>
      <color attach="background" args={["#eef3f7"]} />
      <fog attach="fog" args={["#e7eef3", 22, 46]} />

      <hemisphereLight args={["#ffffff", "#aebccb", 0.9]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[10, 18, 8]}
        intensity={1.15}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-22}
        shadow-camera-right={22}
        shadow-camera-top={22}
        shadow-camera-bottom={-22}
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
        position={[1, 0.18, -1]}
        scale={48}
        far={12}
        blur={2.6}
        opacity={0.32}
        color="#46586d"
      />

      <OrbitControls
        ref={controls}
        enablePan={false}
        minDistance={6}
        maxDistance={34}
        minPolarAngle={0.15}
        maxPolarAngle={Math.PI / 2.15}
        autoRotate={!reduced && selectedId === null}
        autoRotateSpeed={0.35}
        enableDamping
        dampingFactor={0.08}
        target={[1, 0, -1]}
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
      camera={{ position: [2, 15, 19], fov: 38 }}
      gl={{ antialias: true }}
      onPointerMissed={() => setHovered(null)}
    >
      <Scene
        patients={patients}
        selectedId={selectedId}
        statusFilter={statusFilter}
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
    <Html position={[placed.x, placed.y + 0.4 + beamH, placed.z]} center distanceFactor={14}>
      <div className="marker-tip">
        {patient.name}
        <div className="tip-status">
          {meta.glyph} {meta.label} · {patient.district}
        </div>
      </div>
    </Html>
  );
}
