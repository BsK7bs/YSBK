import React, { useMemo, useRef, useState, Suspense } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, Html, Line, Sparkles, Environment } from "@react-three/drei";
import * as THREE from "three";
import DeviceDetailsModal from "./DeviceDetailsModal";

/* ------------------------------------------------------------------ */
/*  Scene: network of glowing digital-twin nodes around a central hub */
/* ------------------------------------------------------------------ */

// Deterministic node positions on two orbital rings + a few extras
function buildNodes() {
  const inner = 8;   // ring count
  const outer = 8;
  const nodes = [];
  const rInner = 2.2;
  const rOuter = 3.6;

  for (let i = 0; i < inner; i++) {
    const a = (i / inner) * Math.PI * 2;
    nodes.push({
      id: `i${i}`,
      pos: [Math.cos(a) * rInner, Math.sin(a * 1.3) * 0.6, Math.sin(a) * rInner],
      tone: i % 3, // 0 = primary, 1 = info, 2 = success
      speed: 0.5 + Math.random() * 0.4,
    });
  }
  for (let i = 0; i < outer; i++) {
    const a = (i / outer) * Math.PI * 2 + Math.PI / outer;
    nodes.push({
      id: `o${i}`,
      pos: [Math.cos(a) * rOuter, Math.cos(a * 1.7) * 1.1, Math.sin(a) * rOuter],
      tone: (i + 1) % 3,
      speed: 0.3 + Math.random() * 0.4,
    });
  }
  return nodes;
}

const TONE_COLORS = ["#22a5ff", "#4dd0e1", "#4ade80"]; // primary, info, chart-3
const TONE_LABELS = ["CPU 42%", "TEMP 63°C", "RAM 61%", "HEALTH 94", "SSD OK", "NET 1G", "GPU 38%", "PWR 45W"];

/* ---------- Node (glowing screen billboarded toward camera) ---------- */
function Node({ position, color, index, hovered, setHovered, onClick, dim }) {
  const ref = useRef();
  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.elapsedTime;
    // Subtle float
    ref.current.position.y = position[1] + Math.sin(t * 0.7 + index) * 0.08;
    // Face camera
    ref.current.lookAt(state.camera.position);
  });

  const isHovered = hovered === index;
  const scaleActive = isHovered ? 1.2 : 1;
  const opacity = dim ? 0.25 : 1;

  return (
    <group ref={ref} position={position}>
      {/* Screen backdrop */}
      <mesh
        onPointerOver={(e) => { e.stopPropagation(); setHovered(index); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { setHovered(null); document.body.style.cursor = 'default'; }}
        onClick={(e) => { e.stopPropagation(); onClick?.(index, position); }}
        scale={scaleActive}
      >
        <planeGeometry args={[0.42, 0.28]} />
        <meshBasicMaterial color="#0b1220" transparent opacity={0.92 * opacity} />
      </mesh>
      {/* Frame */}
      <mesh position={[0, 0, -0.001]}>
        <planeGeometry args={[0.46, 0.32]} />
        <meshBasicMaterial color={color} transparent opacity={(isHovered ? 0.6 : 0.32) * opacity} />
      </mesh>
      {/* Glow */}
      <mesh position={[0, 0, -0.02]}>
        <planeGeometry args={[1.2, 0.9]} />
        <meshBasicMaterial color={color} transparent opacity={(isHovered ? 0.13 : 0.06) * opacity} depthWrite={false} />
      </mesh>
      {/* Screen bars (fake dashboard) */}
      <mesh position={[-0.10, 0.05, 0.001]}>
        <planeGeometry args={[0.035, 0.10]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh position={[-0.04, 0.03, 0.001]}>
        <planeGeometry args={[0.035, 0.14]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh position={[0.02, 0.05, 0.001]}>
        <planeGeometry args={[0.035, 0.10]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh position={[0.08, 0.04, 0.001]}>
        <planeGeometry args={[0.035, 0.12]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {/* Baseline */}
      <mesh position={[0, -0.08, 0.001]}>
        <planeGeometry args={[0.34, 0.012]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.4} />
      </mesh>
      {/* Corner dot indicator */}
      <mesh position={[-0.19, 0.12, 0.002]}>
        <circleGeometry args={[0.012, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {isHovered && (
        <Html center distanceFactor={10} position={[0, -0.32, 0]} pointerEvents="none">
          <div
            className="pointer-events-none select-none whitespace-nowrap font-mono uppercase tracking-[0.2em]"
            style={{
              fontSize: "7px",
              color: color,
              textShadow: `0 0 8px ${color}`,
            }}
          >
            {TONE_LABELS[index % TONE_LABELS.length]}
          </div>
        </Html>
      )}
    </group>
  );
}

/* ---------- Central AI hub ---------- */
function Hub() {
  const ref = useRef();
  const ring1 = useRef();
  const ring2 = useRef();
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (ref.current) {
      ref.current.rotation.y = t * 0.3;
      const s = 1 + Math.sin(t * 1.4) * 0.04;
      ref.current.scale.set(s, s, s);
    }
    if (ring1.current) ring1.current.rotation.x = t * 0.4;
    if (ring2.current) ring2.current.rotation.z = -t * 0.35;
  });

  return (
    <group>
      {/* Core sphere */}
      <mesh ref={ref}>
        <icosahedronGeometry args={[0.55, 2]} />
        <meshStandardMaterial
          color="#22a5ff"
          emissive="#22a5ff"
          emissiveIntensity={2.4}
          wireframe
        />
      </mesh>
      {/* Inner solid glow sphere */}
      <mesh scale={0.42}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial color="#3ee0ff" transparent opacity={0.85} />
      </mesh>
      {/* Outer glow halo */}
      <mesh>
        <sphereGeometry args={[0.9, 24, 24]} />
        <meshBasicMaterial color="#22a5ff" transparent opacity={0.08} depthWrite={false} />
      </mesh>
      {/* Rings */}
      <mesh ref={ring1} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.1, 0.008, 8, 96]} />
        <meshBasicMaterial color="#4dd0e1" transparent opacity={0.75} />
      </mesh>
      <mesh ref={ring2} rotation={[0, Math.PI / 2, Math.PI / 6]}>
        <torusGeometry args={[1.35, 0.006, 8, 96]} />
        <meshBasicMaterial color="#22a5ff" transparent opacity={0.55} />
      </mesh>
    </group>
  );
}

/* ---------- Animated connection line + data pulse ---------- */
function Connection({ from, to, color, delay = 0 }) {
  const pulseRef = useRef();
  const points = useMemo(() => [new THREE.Vector3(...from), new THREE.Vector3(...to)], [from, to]);

  useFrame((state) => {
    if (!pulseRef.current) return;
    const t = (state.clock.elapsedTime + delay) % 3;
    const p = t / 3;
    const eased = p * p * (3 - 2 * p); // smoothstep
    const pos = points[0].clone().lerp(points[1], eased);
    pulseRef.current.position.copy(pos);
    // Fade at ends
    const opacity = Math.sin(p * Math.PI) * 0.9;
    pulseRef.current.material.opacity = opacity;
    const s = 0.7 + Math.sin(p * Math.PI) * 0.7;
    pulseRef.current.scale.set(s, s, s);
  });

  return (
    <>
      <Line
        points={points}
        color={color}
        lineWidth={1}
        transparent
        opacity={0.22}
        dashed={false}
      />
      <mesh ref={pulseRef}>
        <sphereGeometry args={[0.045, 12, 12]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} />
      </mesh>
    </>
  );
}

/* ---------- The rotating orb of nodes ---------- */
function OrbitGroup({ mouse, selectedIndex, onNodeClick }) {
  const group = useRef();
  const nodes = useMemo(() => buildNodes(), []);
  const [hovered, setHovered] = useState(null);

  useFrame((state) => {
    if (!group.current) return;
    const t = state.clock.elapsedTime;
    // Slow autorotation (pause when a node is selected)
    if (selectedIndex == null) {
      group.current.rotation.y = t * 0.12;
    }
    // mouse tilt (target then damped) — disabled while zoomed in
    const strength = selectedIndex == null ? 1 : 0.15;
    const targetX = mouse.current.y * 0.25 * strength;
    const targetY = mouse.current.x * 0.35 * strength;
    group.current.rotation.x += (targetX - group.current.rotation.x) * 0.04;
    group.current.rotation.z += (targetY * 0.1 - group.current.rotation.z) * 0.04;
  });

  return (
    <group ref={group}>
      <Hub />
      {nodes.map((n, i) => (
        <Node
          key={n.id}
          index={i}
          position={n.pos}
          color={TONE_COLORS[n.tone]}
          hovered={hovered}
          setHovered={setHovered}
          onClick={onNodeClick}
          dim={selectedIndex != null && selectedIndex !== i}
        />
      ))}
      {nodes.map((n, i) => (
        <Connection
          key={"c" + n.id}
          from={[0, 0, 0]}
          to={n.pos}
          color={TONE_COLORS[n.tone]}
          delay={i * 0.18}
        />
      ))}
    </group>
  );
}

/* ---------- Mouse-follow camera + zoom to selected ---------- */
function CameraRig({ mouse, target }) {
  useFrame((state) => {
    const cam = state.camera;
    let tx, ty, tz, lookX, lookY, lookZ;
    if (target) {
      // Fly camera to a point in front of the target, at 1.6 units in front of it
      const [x, y, z] = target;
      // Direction from origin to target (target's outward normal)
      const len = Math.max(0.001, Math.hypot(x, y, z));
      const ox = x / len, oy = y / len, oz = z / len;
      // Camera position = target + outward * 1.9
      tx = x + ox * 1.9;
      ty = y + oy * 1.9 + 0.05;
      tz = z + oz * 1.9;
      lookX = x; lookY = y; lookZ = z;
    } else {
      tx = mouse.current.x * 0.35;
      ty = -mouse.current.y * 0.25 + 0.4;
      tz = 7.2;
      lookX = 0; lookY = 0; lookZ = 0;
    }
    cam.position.x += (tx - cam.position.x) * 0.06;
    cam.position.y += (ty - cam.position.y) * 0.06;
    cam.position.z += (tz - cam.position.z) * 0.06;
    cam.lookAt(lookX, lookY, lookZ);
  });
  return null;
}

/* ---------- Main exported component ---------- */
export default function HeroScene3D() {
  const mouse = useRef({ x: 0, y: 0 });
  const [selected, setSelected] = useState(null); // { index, position, nodeId }

  const onPointerMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    mouse.current.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    mouse.current.y = ((e.clientY - r.top) / r.height) * 2 - 1;
  };

  const handleNodeClick = (index, position) => {
    setSelected({ index, position, nodeId: `dt-node-${index}` });
  };

  return (
    <div
      className="relative w-full h-[440px] sm:h-[520px] lg:h-[560px] rounded-3xl overflow-hidden"
      onPointerMove={onPointerMove}
      data-testid="hero-3d-scene"
    >
      <Canvas
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        camera={{ position: [0, 0.4, 7.2], fov: 45 }}
      >
        <color attach="background" args={["#000000"]} />
        <fog attach="fog" args={["#000814", 6.5, 14]} />

        <ambientLight intensity={0.5} />
        <pointLight position={[6, 5, 4]} intensity={1.2} color="#22a5ff" />
        <pointLight position={[-6, -3, -4]} intensity={0.9} color="#4dd0e1" />

        <Suspense fallback={null}>
          <Float speed={0.6} rotationIntensity={0.15} floatIntensity={0.35}>
            <OrbitGroup
              mouse={mouse}
              selectedIndex={selected?.index ?? null}
              onNodeClick={handleNodeClick}
            />
          </Float>
          <Sparkles
            count={140}
            scale={[16, 10, 12]}
            size={2.4}
            speed={0.35}
            opacity={0.7}
            color="#7dd3fc"
          />
        </Suspense>

        <CameraRig mouse={mouse} target={selected?.position ?? null} />
      </Canvas>

      {/* Overlays: subtle vignette + scanline */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)",
        }}
      />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.05] mix-blend-overlay"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(255,255,255,0.6) 0 1px, transparent 1px 3px)",
        }}
      />
      {/* Corner HUD label */}
      <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-cyan-300/70 font-mono">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inset-0 rounded-full bg-cyan-400 animate-ping-soft" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-cyan-400" />
        </span>
        Digital Twin Network · Live
      </div>
      <div className="pointer-events-none absolute right-4 bottom-4 text-[10px] uppercase tracking-[0.22em] text-cyan-300/50 font-mono">
        {selected ? "Streaming from selected node…" : "Click any node to inspect"}
      </div>

      {/* Device details modal */}
      <DeviceDetailsModal
        open={!!selected}
        nodeId={selected?.nodeId}
        nodeIndex={selected?.index ?? 0}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
