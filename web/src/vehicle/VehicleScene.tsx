import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Html } from '@react-three/drei'
import * as THREE from 'three'

export type VehicleSnapshot = {
  climate_power?: boolean
  temperature_setpoint?: number
  cabin_temperature?: number
  fan_level?: number
  window_front_left?: number
  window_front_right?: number
  window_rear_left?: number
  window_rear_right?: number
  media_playing?: boolean
  media_track?: string | null
  media_artist?: string | null
  media_volume?: number
  navigation_active?: boolean
  navigation_destination?: string | null
  route_points?: Array<[number, number] | number[]>
  prompt_enabled?: boolean
  revision?: number
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function WindowPane({
  position,
  openRatio,
  side,
}: {
  position: [number, number, number]
  openRatio: number
  side: 'left' | 'right'
}) {
  const drop = (Math.max(0, Math.min(100, openRatio)) / 100) * 0.55
  const x = side === 'left' ? position[0] - 0.02 : position[0] + 0.02
  return (
    <mesh position={[x, position[1] - drop, position[2]]} castShadow>
      <boxGeometry args={[0.04, 0.55, 0.7]} />
      <meshPhysicalMaterial
        color="#8ecae6"
        transparent
        opacity={0.45}
        roughness={0.1}
        metalness={0.2}
        transmission={0.4}
      />
    </mesh>
  )
}

function Airflow({ power, fan }: { power: boolean; fan: number }) {
  const ref = useRef<THREE.Points>(null)
  const count = 48
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 0.6
      arr[i * 3 + 1] = Math.random() * 0.4
      arr[i * 3 + 2] = (Math.random() - 0.5) * 0.4
    }
    return arr
  }, [])
  useFrame((_, dt) => {
    if (!ref.current || !power) return
    const attr = ref.current.geometry.attributes.position as THREE.BufferAttribute
    const speed = 0.4 + fan * 0.25
    for (let i = 0; i < count; i++) {
      let y = attr.getY(i) + dt * speed
      if (y > 0.55) y = 0
      attr.setY(i, y)
    }
    attr.needsUpdate = true
  })
  if (!power) return null
  return (
    <points ref={ref} position={[0, 0.55, 0.35]}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color="#7fdbda" size={0.035} transparent opacity={0.75} />
    </points>
  )
}

function Spectrum({ playing, volume }: { playing: boolean; volume: number }) {
  const bars = 8
  const refs = useRef<THREE.Mesh[]>([])
  useFrame(({ clock }) => {
    if (!playing) {
      refs.current.forEach((m) => {
        if (m) m.scale.y = lerp(m.scale.y, 0.15, 0.1)
      })
      return
    }
    const t = clock.getElapsedTime()
    refs.current.forEach((m, i) => {
      if (!m) return
      const h = 0.2 + Math.abs(Math.sin(t * (2 + i * 0.4) + i)) * (0.4 + volume * 0.05)
      m.scale.y = lerp(m.scale.y, h, 0.2)
    })
  })
  return (
    <group position={[0, 0.62, 0.42]}>
      {Array.from({ length: bars }).map((_, i) => (
        <mesh
          key={i}
          ref={(el) => {
            if (el) refs.current[i] = el
          }}
          position={[(i - bars / 2) * 0.08 + 0.04, 0, 0]}
        >
          <boxGeometry args={[0.05, 1, 0.05]} />
          <meshStandardMaterial color="#2a9d8f" emissive="#2a9d8f" emissiveIntensity={playing ? 0.4 : 0} />
        </mesh>
      ))}
    </group>
  )
}

function NavRoute({
  active,
  points,
  destination,
}: {
  active: boolean
  points: Array<[number, number] | number[]>
  destination?: string | null
}) {
  if (!active || !points?.length) return null
  return (
    <group position={[2.2, 0.02, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[1.2, 32]} />
        <meshStandardMaterial color="#d8e2dc" />
      </mesh>
      {points.map((p, i) => (
        <mesh key={i} position={[Number(p[0]) * 0.35, 0.05, Number(p[1]) * 0.35]}>
          <sphereGeometry args={[0.06, 12, 12]} />
          <meshStandardMaterial color={i === points.length - 1 ? '#e76f51' : '#f4a261'} />
        </mesh>
      ))}
      {destination ? (
        <Html position={[0, 0.35, 0]} center>
          <div className="vehicle-hud-chip">{destination}</div>
        </Html>
      ) : null}
    </group>
  )
}

function CarBody({ state }: { state: VehicleSnapshot }) {
  const fl = Number(state.window_front_left ?? 0)
  const fr = Number(state.window_front_right ?? 0)
  const rl = Number(state.window_rear_left ?? 0)
  const rr = Number(state.window_rear_right ?? 0)
  const power = Boolean(state.climate_power)
  const playing = Boolean(state.media_playing)
  const navActive = Boolean(state.navigation_active)

  return (
    <group>
      {/* body shell */}
      <mesh position={[0, 0.45, 0]} castShadow receiveShadow>
        <boxGeometry args={[1.6, 0.55, 3.2]} />
        <meshStandardMaterial color="#3d405b" metalness={0.55} roughness={0.35} />
      </mesh>
      {/* cabin glass shell (cutaway) */}
      <mesh position={[0, 0.95, -0.1]} castShadow>
        <boxGeometry args={[1.35, 0.7, 1.8]} />
        <meshPhysicalMaterial color="#a8dadc" transparent opacity={0.22} roughness={0.05} metalness={0.1} />
      </mesh>
      {/* seats */}
      {[-0.35, 0.35].map((x) => (
        <mesh key={x} position={[x, 0.55, 0.15]} castShadow>
          <boxGeometry args={[0.45, 0.35, 0.5]} />
          <meshStandardMaterial color="#264653" />
        </mesh>
      ))}
      {/* dashboard / screen */}
      <mesh position={[0, 0.72, 0.85]} castShadow>
        <boxGeometry args={[0.9, 0.35, 0.08]} />
        <meshStandardMaterial color="#111827" emissive={playing || navActive ? '#1d3557' : '#000'} emissiveIntensity={0.5} />
      </mesh>
      <Html position={[0, 0.72, 0.9]} center transform occlude distanceFactor={4}>
        <div className="vehicle-screen">
          <div className="vehicle-screen-title">中控</div>
          <div>
            设定 {Number(state.temperature_setpoint ?? 0)}℃ / 舱温 {Number(state.cabin_temperature ?? 0)}℃
          </div>
          <div>
            {playing
              ? `♪ ${state.media_artist ?? '播放中'} · ${state.media_track ?? ''}`
              : '媒体暂停'}
          </div>
          <div>
            {navActive ? `导航 → ${state.navigation_destination ?? '途中'}` : '导航未启动'}
          </div>
        </div>
      </Html>

      <WindowPane position={[-0.78, 0.95, 0.35]} openRatio={fl} side="left" />
      <WindowPane position={[0.78, 0.95, 0.35]} openRatio={fr} side="right" />
      <WindowPane position={[-0.78, 0.95, -0.55]} openRatio={rl} side="left" />
      <WindowPane position={[0.78, 0.95, -0.55]} openRatio={rr} side="right" />

      <Airflow power={power} fan={Number(state.fan_level ?? 0)} />
      <Spectrum playing={playing} volume={Number(state.media_volume ?? 0)} />
      <NavRoute
        active={navActive}
        points={(state.route_points as Array<[number, number]>) ?? []}
        destination={state.navigation_destination}
      />

      <Html position={[-1.4, 1.6, 0]} center>
        <div className="vehicle-hud">
          <div>空调电源：{power ? '开' : '关'}</div>
          <div>
            设定 {Number(state.temperature_setpoint ?? 0)}℃ ≠ 舱温 {Number(state.cabin_temperature ?? 0)}℃
          </div>
          <div>
            车窗 L {fl}/{rl} · R {fr}/{rr}
          </div>
        </div>
      </Html>
    </group>
  )
}

function SceneContent({ state }: { state: VehicleSnapshot }) {
  return (
    <>
      <color attach="background" args={['#e9eef2']} />
      <ambientLight intensity={0.65} />
      <directionalLight position={[4, 8, 3]} intensity={1.1} castShadow />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial color="#cfd8dc" />
      </mesh>
      <CarBody state={state} />
      <OrbitControls enablePan={false} minDistance={3} maxDistance={10} maxPolarAngle={Math.PI / 2.1} />
      <Html position={[0, 2.2, 0]} center>
        <div className="vehicle-hud-chip">Simulator Snapshot → 3D（非 Tool ACK）</div>
      </Html>
    </>
  )
}

export function VehicleScene({ state }: { state: VehicleSnapshot }) {
  return (
    <div className="vehicle-canvas">
      <Canvas shadows camera={{ position: [3.8, 2.6, 4.2], fov: 42 }}>
        <SceneContent state={state} />
      </Canvas>
    </div>
  )
}

export function snapshotFromDevice(device: { state?: Record<string, unknown> } | null): VehicleSnapshot {
  const s = device?.state ?? {}
  return {
    climate_power: Boolean(s.climate_power),
    temperature_setpoint: Number(s.temperature_setpoint ?? 0),
    cabin_temperature: Number(s.cabin_temperature ?? 0),
    fan_level: Number(s.fan_level ?? 0),
    window_front_left: Number(s.window_front_left ?? 0),
    window_front_right: Number(s.window_front_right ?? 0),
    window_rear_left: Number(s.window_rear_left ?? 0),
    window_rear_right: Number(s.window_rear_right ?? 0),
    media_playing: Boolean(s.media_playing),
    media_track: (s.media_track as string) ?? null,
    media_artist: (s.media_artist as string) ?? null,
    media_volume: Number(s.media_volume ?? 0),
    navigation_active: Boolean(s.navigation_active),
    navigation_destination: (s.navigation_destination as string) ?? null,
    route_points: (s.route_points as Array<[number, number]>) ?? [],
    prompt_enabled: Boolean(s.prompt_enabled),
  }
}
