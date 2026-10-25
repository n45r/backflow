export default function build(THREE, root, site) {
  const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.9, ...o });
  const box = (x0, x1, y0, y1, z0, z1, m) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0), m);
    mesh.position.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
    root.add(mesh);
    return mesh;
  };

  const FLOOR_Y = -2.5, SLOPE = 0.015, DRAIN = [6, 2.5];
  const BX0 = 3, BX1 = 9, BZ0 = 1, BZ1 = 7;

  // ground with a hole over the basement
  const shape = new THREE.Shape();
  shape.moveTo(-12.5, -12.5); shape.lineTo(12.5, -12.5); shape.lineTo(12.5, 12.5); shape.lineTo(-12.5, 12.5); shape.lineTo(-12.5, -12.5);
  const hole = new THREE.Path();
  hole.moveTo(BX0, -BZ0); hole.lineTo(BX1, -BZ0); hole.lineTo(BX1, -BZ1); hole.lineTo(BX0, -BZ1); hole.lineTo(BX0, -BZ0);
  shape.holes.push(hole);
  const gg = new THREE.ShapeGeometry(shape);
  gg.rotateX(-Math.PI / 2);
  const ground = new THREE.Mesh(gg, mat(0x6f8f4e, { side: THREE.DoubleSide }));
  ground.position.y = 0;
  root.add(ground);

  // pond bed and banks
  box(-10, -3, -0.02, 0.03, -8, -2, mat(0x5b4a38));
  box(-10.2, -9.8, 0, 0.9, -8, -2, mat(0x8a7a66));
  box(-10, -3, 0, 0.9, -8.2, -7.8, mat(0x8a7a66));
  box(-10, -3, 0, 0.9, -2.2, -1.8, mat(0x8a7a66));
  // weir wall (crest 0.51 m)
  box(-3.2, -2.8, 0, 0.51, -8, -2, mat(0xb8b8b0));
  // channel
  box(-2.8, 4, -0.02, 0.02, -6, -4, mat(0x4a4a4a));
  box(-2.8, 4, 0, 0.35, -6.2, -5.9, mat(0xa0a09a));
  box(-2.8, 4, 0, 0.35, -4.1, -3.8, mat(0xa0a09a));

  // building above ground, north of the basement opening
  box(BX0, BX1, 0, 3, -3, 0.9, mat(0xd8cfc0));
  // roof slab over the rear part of the basement is omitted so the room is open (cutaway)

  // basement walls (rear, left, right; front open)
  const wallM = mat(0xcfc7b8);
  box(BX0 - 0.2, BX1 + 0.2, FLOOR_Y - 0.2, 0, BZ0 - 0.2, BZ0, wallM);
  box(BX0 - 0.2, BX0, FLOOR_Y - 0.2, 0, BZ0, BZ1, wallM);
  box(BX1, BX1 + 0.2, FLOOR_Y - 0.2, 0, BZ0, BZ1, wallM);

  // sloped basement floor
  const N = 30;
  const pos = [], idx = [];
  for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
    const x = BX0 + (BX1 - BX0) * i / N, z = BZ0 + (BZ1 - BZ0) * j / N;
    const d = Math.hypot(x - DRAIN[0], z - DRAIN[1]);
    pos.push(x, FLOOR_Y + SLOPE * d, z);
  }
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
    const a = i * (N + 1) + j, b = a + 1, c = a + N + 1, d = c + 1;
    idx.push(a, b, c, b, d, c);
  }
  const fg = new THREE.BufferGeometry();
  fg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  fg.setIndex(idx);
  fg.computeVertexNormals();
  root.add(new THREE.Mesh(fg, mat(0x77706a, { side: THREE.DoubleSide })));
  // drain
  const drain = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.02, 24), mat(0x111111));
  drain.position.set(DRAIN[0], FLOOR_Y + 0.012, DRAIN[1]);
  root.add(drain);
  // furniture for scale
  box(7.2, 8.8, FLOOR_Y + 0.05, FLOOR_Y + 0.9, 1.3, 2.3, mat(0x9b6b3a));

  // manhole
  const mh = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 0.04, 32), mat(0x2b2b2b));
  mh.position.set(-1, 0.02, 3);
  root.add(mh);

  const outline = [[BX0, BZ0], [BX1, BZ0], [BX1, BZ1], [BX0, BZ1]];
  return {
    cameras: {
      cam1: { position: [-6, 4.5, 6], lookAt: [-4.5, 0, -4], fov: 60 },
      cam5: { position: [6, 3.8, 10.5], lookAt: [6, -2.4, 3], fov: 70 },
    },
    water: {
      pond: { outline: [[-10, -8], [-3.2, -8], [-3.2, -2], [-10, -2]], base_y: 0.03 },
      basement: { outline, floor_y: FLOOR_Y, slope: SLOPE, drain_xz: DRAIN },
      manhole_m2: { center: [-1, 3], radius: 0.4, base_y: 0.04 },
    },
    materials: { water: { color: '#3a7bd5', opacity: 0.6 } },
  };
}
