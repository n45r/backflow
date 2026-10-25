export default function build(THREE, root, site = {}) {
  const toY = (elev) => (elev > 100 ? elev - 419.0 : elev);

  const pondBaseY = 0.0;
  const weirCrestM = site?.weir_crest_m != null ? site.weir_crest_m : 0.51;
  const weirCrestY = pondBaseY + weirCrestM;

  const doorThresholdY =
    site?.door_threshold_m != null ? toY(site.door_threshold_m) : toY(419.8);
  const basementFloorY =
    site?.basement_floor_m != null ? toY(site.basement_floor_m) : toY(418.44);
  const basementSlope =
    site?.basement_floor_slope != null ? site.basement_floor_slope : 0.01;
  const drainXZ =
    Array.isArray(site?.basement_drain_xy) && site.basement_drain_xy.length >= 2
      ? [site.basement_drain_xy[0], site.basement_drain_xy[1]]
      : [14.1, 5.6];
  const pipeP7Dia =
    site?.pipe_p7_diameter_m != null ? site.pipe_p7_diameter_m : 0.1472;
  const pondAreaM2 = site?.pond_area_m2 != null ? site.pond_area_m2 : 8.5;

  // Pond (Storage s3) dimensions derived from plan width 3.49m and site.pond_area_m2
  const pondX0 = 9.0;
  const pondWidthX = 3.49;
  const pondX1 = pondX0 + pondWidthX;
  const pondDepthZ = pondAreaM2 / pondWidthX;
  const pondZ1 = 22.45;
  const pondZ0 = pondZ1 - pondDepthZ;

  // Materials (MeshStandardMaterial with plain colours resembling concrete, grass, wood, metal)
  const matConcrete = new THREE.MeshStandardMaterial({
    color: 0x9a9d98,
    roughness: 0.85,
    metalness: 0.05
  });
  const matConcreteLight = new THREE.MeshStandardMaterial({
    color: 0xbabcb6,
    roughness: 0.8,
    metalness: 0.05
  });
  const matConcreteDark = new THREE.MeshStandardMaterial({
    color: 0x595c58,
    roughness: 0.9,
    metalness: 0.05
  });
  const matBasementFloor = new THREE.MeshStandardMaterial({
    color: 0x626562,
    roughness: 0.88,
    metalness: 0.05
  });
  const matBasementBackFloor = new THREE.MeshStandardMaterial({
    color: 0x3b3d3b,
    roughness: 0.9,
    metalness: 0.05
  });
  const matChannel = new THREE.MeshStandardMaterial({
    color: 0x888c86,
    roughness: 0.85,
    metalness: 0.05
  });
  const matGrass = new THREE.MeshStandardMaterial({
    color: 0x5c7a46,
    roughness: 0.95,
    metalness: 0.0
  });
  const matWood = new THREE.MeshStandardMaterial({
    color: 0x99958f,
    roughness: 0.82,
    metalness: 0.05
  });
  const matMetal = new THREE.MeshStandardMaterial({
    color: 0x3a3d40,
    roughness: 0.45,
    metalness: 0.75
  });
  const matDarkHole = new THREE.MeshStandardMaterial({
    color: 0x161818,
    roughness: 0.95,
    metalness: 0.1
  });
  const matSandbag = new THREE.MeshStandardMaterial({
    color: 0x242628,
    roughness: 0.9,
    metalness: 0.05
  });
  const matShutter = new THREE.MeshStandardMaterial({
    color: 0x5a5c5a,
    roughness: 0.65,
    metalness: 0.35
  });
  const matWhite = new THREE.MeshStandardMaterial({
    color: 0xdcded8,
    roughness: 0.6,
    metalness: 0.1
  });

  // Lights (one hemisphere light and one directional light)
  const hemiLight = new THREE.HemisphereLight(0xdde6f0, 0x555852, 0.85);
  hemiLight.name = "hemisphere_light";
  hemiLight.position.set(12.25, 20.0, 11.35);
  root.add(hemiLight);

  const dirLight = new THREE.DirectionalLight(0xfff8eb, 0.95);
  dirLight.name = "directional_light";
  dirLight.position.set(18.0, 24.0, 16.0);
  root.add(dirLight);

  // Helper to create named axis-aligned boxes from min/max coordinates
  function addBox(name, x0, x1, y0, y1, z0, z1, material, parent = root) {
    const w = Math.abs(x1 - x0);
    const h = Math.abs(y1 - y0);
    const d = Math.abs(z1 - z0);
    const geom = new THREE.BoxGeometry(w, h, d);
    const mesh = new THREE.Mesh(geom, material);
    mesh.name = name;
    mesh.position.set((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5);
    parent.add(mesh);
    return mesh;
  }

  // Helper to create sloped quad slabs
  function addSlopedSlab(
    name,
    x0,
    x1,
    z0,
    z1,
    yNW,
    yNE,
    ySE,
    ySW,
    thickness,
    material,
    parent = root
  ) {
    const geom = new THREE.BufferGeometry();
    const bNW = yNW - thickness;
    const bNE = yNE - thickness;
    const bSE = ySE - thickness;
    const bSW = ySW - thickness;

    const vertices = new Float32Array([
      // Top face
      x0, yNW, z0,
      x0, ySW, z1,
      x1, ySE, z1,
      x0, yNW, z0,
      x1, ySE, z1,
      x1, yNE, z0,
      // Bottom face
      x0, bNW, z0,
      x1, bSE, z1,
      x0, bSW, z1,
      x0, bNW, z0,
      x1, bNE, z0,
      x1, bSE, z1,
      // North face
      x0, yNW, z0,
      x1, yNE, z0,
      x1, bNE, z0,
      x0, yNW, z0,
      x1, bNE, z0,
      x0, bNW, z0,
      // South face
      x0, ySW, z1,
      x0, bSW, z1,
      x1, bSE, z1,
      x0, ySW, z1,
      x1, bSE, z1,
      x1, ySE, z1,
      // West face
      x0, yNW, z0,
      x0, bNW, z0,
      x0, bSW, z1,
      x0, yNW, z0,
      x0, bSW, z1,
      x0, ySW, z1,
      // East face
      x1, yNE, z0,
      x1, ySE, z1,
      x1, bSE, z1,
      x1, yNE, z0,
      x1, bSE, z1,
      x1, bNE, z0
    ]);
    geom.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
    geom.computeVertexNormals();
    const mesh = new THREE.Mesh(geom, material);
    mesh.name = name;
    parent.add(mesh);
    return mesh;
  }

  // Helper to create manholes (as rims and dark openings)
  function addManhole(name, cx, cz, radius, rimY, baseY, parent = root) {
    const group = new THREE.Group();
    group.name = name;

    const depth = Math.max(0.25, rimY - baseY);
    const rimThickness = 0.06;

    // Outer cast-iron / steel rim ring using lathe/cylinder
    const rimGeom = new THREE.RingGeometry(radius, radius + rimThickness, 32);
    rimGeom.rotateX(-Math.PI / 2);
    const rimMesh = new THREE.Mesh(rimGeom, matMetal);
    rimMesh.name = `${name}_rim`;
    rimMesh.position.set(cx, rimY + 0.004, cz);
    group.add(rimMesh);

    // Inner vertical collar
    const shaftGeom = new THREE.CylinderGeometry(
      radius,
      radius,
      depth,
      32,
      1,
      true
    );
    const shaftMat = new THREE.MeshStandardMaterial({
      color: 0x454845,
      roughness: 0.9,
      metalness: 0.1,
      side: THREE.DoubleSide
    });
    const shaftMesh = new THREE.Mesh(shaftGeom, shaftMat);
    shaftMesh.name = `${name}_shaft`;
    shaftMesh.position.set(cx, rimY - depth * 0.5, cz);
    group.add(shaftMesh);

    // Dark bottom opening
    const bottomGeom = new THREE.CircleGeometry(radius, 32);
    bottomGeom.rotateX(-Math.PI / 2);
    const bottomMesh = new THREE.Mesh(bottomGeom, matDarkHole);
    bottomMesh.name = `${name}_opening`;
    bottomMesh.position.set(cx, baseY + 0.01, cz);
    group.add(bottomMesh);

    parent.add(group);
    return group;
  }

  // 1. Exterior grass apron & base foundation
  addBox("surrounding_grass", 0.0, 24.5, -1.2, -0.8, 0.0, 22.7, matGrass);
  addBox("west_grass_bank", 0.0, 4.35, -0.8, 0.18, 0.0, 22.7, matGrass);

  // 2. Site outer perimeter walls (20.15m main width x 22.70m length, from x=4.35 to 24.50)
  const perimeterGroup = new THREE.Group();
  perimeterGroup.name = "site_perimeter_walls";
  root.add(perimeterGroup);

  addBox("north_outer_wall", 4.35, 24.5, -0.8, 1.4, 0.0, 0.25, matConcrete, perimeterGroup);
  addBox("east_outer_wall", 24.25, 24.5, -0.8, 1.35, 0.0, 22.7, matConcrete, perimeterGroup);
  addBox("south_outer_wall", 4.35, 24.5, -0.8, 1.02, 22.45, 22.7, matConcrete, perimeterGroup);
  addBox("west_outer_wall_upper", 4.35, 4.6, -0.8, 1.1, 0.0, 8.8, matConcrete, perimeterGroup);
  addBox("west_outer_wall_lower", 5.55, 5.8, -0.8, 1.0, 8.8, 22.7, matConcrete, perimeterGroup);

  // 3. Ground surfaces with real slopes from the 1:50 plan
  const groundGroup = new THREE.Group();
  groundGroup.name = "sloped_ground";
  root.add(groundGroup);

  // Lower-right courtyard (1.0% - 1.5% slope, elevations +0.80 to +0.90 -> y = 0.98 to 1.08)
  addSlopedSlab(
    "ground_southeast",
    14.58,
    24.25,
    11.45,
    22.45,
    1.03, // +0.85 (420.03)
    1.08, // +0.90 (420.08)
    1.0,  // +0.82 (420.00)
    1.0,  // +0.82 (420.00)
    0.45,
    matConcrete,
    groundGroup
  );

  // Lower-middle ground north of Pond s3 & Channel c1 (1.5% slope, elevations +0.69 to +0.75 -> y = 0.87 to 0.93)
  addSlopedSlab(
    "ground_middle_west",
    5.8,
    12.5,
    11.45,
    19.8,
    0.91, // +0.73 (419.91)
    0.85, // +0.67 (419.85)
    0.87, // +0.69 (419.87)
    0.92, // +0.74 (419.92)
    0.45,
    matConcrete,
    groundGroup
  );

  // East middle ground beside building (1.5% slope, elevations +0.95 to +1.04 -> y = 1.13 to 1.22)
  addSlopedSlab(
    "ground_northeast_court",
    18.25,
    24.25,
    0.25,
    11.45,
    1.18, // +1.00 (420.18)
    1.19, // +1.01 (420.19)
    1.08, // +0.90 (420.08)
    1.02, // +0.84 (420.02)
    0.45,
    matConcrete,
    groundGroup
  );

  // Upper-west platform between Channel c4 and Staircase (door_threshold_m = 419.8 -> y = 0.80)
  addSlopedSlab(
    "ground_threshold_platform",
    7.45,
    11.45,
    9.0,
    11.45,
    doorThresholdY,
    doorThresholdY + 0.04,
    0.85,
    0.84,
    0.45,
    matConcrete,
    groundGroup
  );

  // Middle dividing wall running east-west at z = 11.20..11.45
  addBox("middle_retaining_wall_west", 5.8, 11.0, 0.2, 1.02, 11.2, 11.45, matConcrete);
  addBox("middle_retaining_wall_east", 15.2, 24.25, 0.2, 1.12, 11.2, 11.45, matConcrete);

  // 4. Storage s3 (The Pond) & Weir w1 & Manhole m1
  const pondGroup = new THREE.Group();
  pondGroup.name = "storage_s3";
  root.add(pondGroup);

  // Pond floor at base_y = 0.0
  addBox("pond_floor", pondX0 - 0.15, 14.58, -0.45, pondBaseY, pondZ0 - 0.15, pondZ1, matConcreteDark, pondGroup);

  // Weir w1 (west wall of Pond s3 separating s3 from Channel c1, crest at weirCrestY = 0.51)
  addBox("weir_w1", pondX0 - 0.15, pondX0, pondBaseY, weirCrestY, pondZ0, pondZ1, matConcreteLight, pondGroup);

  // Pond north, east, and internal baffle walls
  addBox("pond_north_wall", pondX0 - 0.15, 12.2, pondBaseY, 0.88, pondZ0 - 0.2, pondZ0, matConcrete, pondGroup);
  addBox("pond_east_wall", 14.38, 14.58, pondBaseY, 1.0, pondZ0 - 0.2, pondZ1, matConcrete, pondGroup);
  addBox("pond_baffle_wall", pondX1, pondX1 + 0.12, pondBaseY, 0.42, pondZ0, pondZ1 - 0.47, matConcrete, pondGroup);

  // Orifice r1 & r2 and Pipe p2 inside east chamber of Storage s3
  const pipeP2Geom = new THREE.CylinderGeometry(0.08, 0.08, pondDepthZ, 16);
  pipeP2Geom.rotateX(Math.PI / 2);
  const pipeP2 = new THREE.Mesh(pipeP2Geom, matMetal);
  pipeP2.name = "pipe_p2";
  pipeP2.position.set(12.75, pondBaseY + 0.12, (pondZ0 + pondZ1) * 0.5);
  pondGroup.add(pipeP2);

  // Manhole m1 at north-east inlet of Storage s3
  addManhole("manhole_m1", 12.6, pondZ0 - 0.25, 0.35, 0.85, pondBaseY, pondGroup);

  // Camera 1 mounting post on the east edge of Storage s3 (s3_cam1_instar)
  addBox("cam1_post", 14.55, 14.68, 1.0, 2.25, 21.05, 21.18, matMetal, pondGroup);

  // 5. Lower Channel c1, Weir w4, and Shaft s2 (west of Weir w1)
  const channelC1Lower = new THREE.Group();
  channelC1Lower.name = "channel_c1_lower";
  root.add(channelC1Lower);

  // Channel c1 floor at +0.00 (419.18 -> y = 0.18)
  addBox("channel_c1_floor", 5.8, pondX0 - 0.15, -0.35, 0.18, 21.35, 22.45, matChannel, channelC1Lower);
  // Sloped northern bank of Channel c1 (12% slope from y=0.87 down to y=0.18)
  addSlopedSlab(
    "channel_c1_north_slope",
    5.8,
    pondX0 - 0.15,
    19.8,
    21.35,
    0.87,
    0.87,
    0.18,
    0.18,
    0.35,
    matChannel,
    channelC1Lower
  );

  // Weir w4 & Shaft s2 at bottom-left
  addBox("weir_w4", 5.75, 5.9, 0.18, 0.58, 21.35, 22.45, matConcreteLight, channelC1Lower);
  addBox("shaft_s2", 4.6, 5.75, -0.4, 0.12, 21.35, 22.45, matConcreteDark, channelC1Lower);

  // 6. Storage s4, Manhole m2, Orifice r3, Weir w2, Channel c3, Curbstone 12cm, and Diagonal Channel c1
  const centerGroup = new THREE.Group();
  centerGroup.name = "central_channels_and_m2";
  root.add(centerGroup);

  const m2Center = [14.0, 10.4];
  const m2Radius = 0.4;
  const m2BaseY = -0.2;

  // Storage s4 recess around Manhole m2
  addBox("storage_s4_floor", 11.0, 15.2, 0.3, 0.75, 9.25, 11.2, matConcrete, centerGroup);
  addManhole("manhole_m2", m2Center[0], m2Center[1], m2Radius, 0.78, m2BaseY, centerGroup);

  // Weir w2 between Storage s4 / Manhole m2 and Channel c3
  addBox("weir_w2", 13.4, 14.6, 0.75, 0.9, 11.15, 11.3, matConcreteLight, centerGroup);

  // Channel c3 (width 1.10m, z = 11.30 to 12.40, x = 10.80 to 15.20)
  addBox("channel_c3", 10.8, 15.2, 0.4, 0.76, 11.3, 12.4, matChannel, centerGroup);

  // Curbstone height 12cm along south edge of Channel c3 (length 4.6m)
  addBox("curbstone_c3", 9.6, 14.2, 0.85, 0.85 + 0.12, 12.4, 12.55, matConcreteLight, centerGroup);

  // Diagonal Channel c1 (length 7.3m, width 1.10m, running from Channel c3 at [14.1, 12.4] to Manhole m1 at [12.6, 19.6])
  const diagDx = 12.6 - 14.1;
  const diagDz = 19.6 - 12.4;
  const diagLen = Math.hypot(diagDx, diagDz);
  const diagAngle = Math.atan2(diagDx, diagDz);

  const diagChannelGroup = new THREE.Group();
  diagChannelGroup.name = "channel_c1_diagonal";
  diagChannelGroup.position.set(13.35, 0.82, 16.0);
  diagChannelGroup.rotation.y = diagAngle;
  centerGroup.add(diagChannelGroup);

  // Channel bed and 12cm side curbstones
  addBox("channel_c1_bed", -0.55, 0.55, -0.15, 0.0, -diagLen * 0.5, diagLen * 0.5, matChannel, diagChannelGroup);
  addBox("channel_c1_curb_west", -0.67, -0.55, 0.0, 0.12, -diagLen * 0.5, diagLen * 0.5, matConcreteLight, diagChannelGroup);
  addBox("channel_c1_curb_east", 0.55, 0.67, 0.0, 0.12, -diagLen * 0.5, diagLen * 0.5, matConcreteLight, diagChannelGroup);

  // 7. Upper-left Storage s5, Weir w3, Channel c4, and Pipe p7
  const northwestGroup = new THREE.Group();
  northwestGroup.name = "storage_s5_and_channel_c4";
  root.add(northwestGroup);

  // Storage s5 basin (width 1.75m, x = 5.45 to 7.20, z = 0.25 to 3.20, elevation 417.96 -> y = -1.04)
  addBox("storage_s5_floor", 5.45, 7.2, -1.2, -1.04, 0.25, 3.2, matConcreteDark, northwestGroup);
  addBox("storage_s5_divider_wall", 5.2, 5.45, -1.04, 1.1, 0.25, 8.8, matConcrete, northwestGroup);
  addBox("storage_s5_east_wall", 7.2, 7.45, -1.04, 1.32, 0.25, 9.25, matConcrete, northwestGroup);

  // Weir w3 separating Storage s5 and Channel c4
  addBox("weir_w3", 5.45, 7.2, -1.04, -0.15, 3.1, 3.3, matConcreteLight, northwestGroup);

  // Channel c4 sloping from north (z=3.30, y=-0.95) to south (z=9.25, y=0.69)
  addSlopedSlab(
    "channel_c4",
    5.45,
    7.2,
    3.3,
    9.25,
    -0.95,
    -0.95,
    0.69,
    0.69,
    0.25,
    matChannel,
    northwestGroup
  );
  addBox("channel_c4_south_extension", 5.8, 10.8, 0.4, 0.72, 9.25, 11.2, matChannel, northwestGroup);

  // Pipe p7 connecting Orifice r5 in Manhole m3 (drainXZ) to Valve v3 (x = 5.30) using site.pipe_p7_diameter_m
  const pipeP7Length = drainXZ[0] - 5.3;
  const pipeP7Geom = new THREE.CylinderGeometry(
    pipeP7Dia * 0.5,
    pipeP7Dia * 0.5,
    pipeP7Length,
    16
  );
  pipeP7Geom.rotateZ(Math.PI / 2);
  const pipeP7 = new THREE.Mesh(pipeP7Geom, matMetal);
  pipeP7.name = "pipe_p7";
  pipeP7.position.set(5.3 + pipeP7Length * 0.5, basementFloorY - 0.25, drainXZ[1]);
  northwestGroup.add(pipeP7);

  // 8. Building, Staircase, and Basement (Storage s6, Manhole m3 / Orifice r5)
  const buildingGroup = new THREE.Group();
  buildingGroup.name = "building_and_storage_s6";
  root.add(buildingGroup);

  // Basement floor (Storage s6) sloping slightly toward drain_xz at Manhole m3
  const bx0 = 11.45;
  const bx1 = 18.0;
  const bz0 = 2.9;
  const bz1 = 9.0;
  const dX = drainXZ[0];
  const dZ = drainXZ[1];

  const elevAt = (x, z) =>
    basementFloorY + Math.hypot(x - dX, z - dZ) * basementSlope;

  // Main foreground basement floor slab with circular cutout at (dX, dZ) for manhole_m3
  const holeRadius = 0.29;
  const floorShape = new THREE.Shape();
  floorShape.moveTo(bx0, 5.2);
  floorShape.lineTo(bx1, 5.2);
  floorShape.lineTo(bx1, bz1);
  floorShape.lineTo(bx0, bz1);
  floorShape.closePath();

  const manholeHole = new THREE.Path();
  manholeHole.absarc(dX, dZ, holeRadius, 0, Math.PI * 2, false);
  floorShape.holes.push(manholeHole);

  const floorGeom = new THREE.ExtrudeGeometry(floorShape, {
    depth: 0.35,
    bevelEnabled: false,
    curveSegments: 32
  });
  floorGeom.rotateX(Math.PI / 2);
  // Adjust vertex Y positions to match the subtle slope toward drainXZ
  const posAttr = floorGeom.attributes.position;
  for (let i = 0; i < posAttr.count; i++) {
    const vx = posAttr.getX(i);
    const vy = posAttr.getY(i); // 0 at top face, -0.35 at bottom face
    const vz = posAttr.getZ(i);
    posAttr.setY(i, elevAt(vx, vz) + vy);
  }
  floorGeom.computeVertexNormals();
  const basementFloorMesh = new THREE.Mesh(floorGeom, matBasementFloor);
  basementFloorMesh.name = "basement_floor";
  buildingGroup.add(basementFloorMesh);

  // Rear-right basement floor slab (visible on the right side of cam5 frame)
  addSlopedSlab(
    "basement_floor_rear_right",
    14.55,
    bx1,
    bz0,
    5.2,
    elevAt(14.55, bz0),
    elevAt(bx1, bz0),
    elevAt(bx1, 5.2),
    elevAt(14.55, 5.2),
    0.35,
    matBasementBackFloor,
    buildingGroup
  );

  // Rear-left basement floor slab
  addSlopedSlab(
    "basement_floor_rear_left",
    bx0,
    14.55,
    bz0,
    5.2,
    elevAt(bx0, bz0),
    elevAt(14.55, bz0),
    elevAt(14.55, 5.2),
    elevAt(bx0, 5.2),
    0.35,
    matBasementFloor,
    buildingGroup
  );

  // Manhole m3 & Orifice r5 at drainXZ (center [14.10, 5.60] matching cam5 frame)
  // Rim and sunken concrete collar raised slightly above the floor surface so it is clearly visible
  const m3Group = addManhole(
    "manhole_m3",
    dX,
    dZ,
    holeRadius,
    elevAt(dX, dZ) + 0.012,
    basementFloorY - 0.16,
    buildingGroup
  );

  // Inner concrete sump shelf inside Manhole m3 (visible in cam5 around the central drain hole)
  const sumpShelfGeom = new THREE.RingGeometry(pipeP7Dia * 0.5, holeRadius - 0.01, 32);
  sumpShelfGeom.rotateX(-Math.PI / 2);
  const sumpShelf = new THREE.Mesh(sumpShelfGeom, matConcreteDark);
  sumpShelf.name = "manhole_m3_sump_shelf";
  sumpShelf.position.set(dX, basementFloorY - 0.11, dZ);
  m3Group.add(sumpShelf);

  // Orifice r5 drain opening at bottom of Manhole m3
  const orificeR5Geom = new THREE.CircleGeometry(pipeP7Dia * 0.5, 24);
  orificeR5Geom.rotateX(-Math.PI / 2);
  const orificeR5 = new THREE.Mesh(orificeR5Geom, matDarkHole);
  orificeR5.name = "orifice_r5";
  orificeR5.position.set(dX, basementFloorY - 0.105, dZ);
  m3Group.add(orificeR5);

  // Vertical striped measuring rod inside Manhole m3 (clearly visible in cam5 frame)
  const rodGroup = new THREE.Group();
  rodGroup.name = "manhole_m3_gauge_rod";
  for (let i = 0; i < 12; i++) {
    const segGeom = new THREE.CylinderGeometry(0.009, 0.009, 0.05, 10);
    const segMesh = new THREE.Mesh(
      segGeom,
      i % 2 === 0 ? matWhite : matDarkHole
    );
    segMesh.position.set(dX, basementFloorY - 0.25 + i * 0.05, dZ);
    rodGroup.add(segMesh);
  }
  buildingGroup.add(rodGroup);

  // Central concrete wall pillar behind Manhole m3 (width 1.25m from x=13.30 to 14.55 at z=5.25, matching cam5)
  addBox(
    "basement_central_pillar",
    13.3,
    14.55,
    basementFloorY,
    2.1,
    2.9,
    5.25,
    matConcreteLight,
    buildingGroup
  );
  // Dark damp plinth strip at bottom of pillar (seen in cam5)
  addBox(
    "basement_pillar_plinth",
    13.3,
    14.55,
    basementFloorY,
    basementFloorY + 0.05,
    5.24,
    5.26,
    matConcreteDark,
    buildingGroup
  );
  // Subtle vertical formwork seam strips on the pillar face (seen in cam5)
  addBox(
    "pillar_seam_1",
    13.71,
    13.73,
    basementFloorY + 0.05,
    2.1,
    5.245,
    5.258,
    matConcrete,
    buildingGroup
  );
  addBox(
    "pillar_seam_2",
    14.13,
    14.15,
    basementFloorY + 0.05,
    2.1,
    5.245,
    5.258,
    matConcrete,
    buildingGroup
  );

  // Wooden door to the left of the concrete pillar (width 1.03m from x=12.27 to 13.30 at z=5.25, matching cam5)
  addBox(
    "basement_wooden_door",
    12.27,
    13.24,
    basementFloorY + 0.03,
    1.75,
    5.18,
    5.24,
    matWood,
    buildingGroup
  );
  addBox(
    "basement_door_frame_right",
    13.24,
    13.3,
    basementFloorY,
    1.8,
    5.2,
    5.26,
    matConcreteDark,
    buildingGroup
  );
  addBox(
    "basement_door_frame_bottom",
    12.27,
    13.3,
    basementFloorY,
    basementFloorY + 0.04,
    5.2,
    5.26,
    matConcreteDark,
    buildingGroup
  );
  // Door handle & wall switch box visible in cam5
  addBox(
    "basement_door_handle",
    12.32,
    12.45,
    basementFloorY + 0.56,
    basementFloorY + 0.62,
    5.24,
    5.29,
    matDarkHole,
    buildingGroup
  );
  addBox(
    "basement_wall_switch",
    13.25,
    13.3,
    basementFloorY + 0.58,
    basementFloorY + 0.68,
    5.25,
    5.29,
    matDarkHole,
    buildingGroup
  );

  // Sandbag, rebar rod, and sensor cables visible in cam5 dry frame (raised above sloped floor surface)
  const sandbag = addBox(
    "basement_sandbag",
    13.32,
    13.72,
    elevAt(13.52, 5.4),
    elevAt(13.52, 5.4) + 0.16,
    5.27,
    5.52,
    matSandbag,
    buildingGroup
  );
  sandbag.rotation.y = 0.08;

  const rebarGeom = new THREE.CylinderGeometry(0.014, 0.014, 1.35, 10);
  rebarGeom.rotateZ(Math.PI / 2);
  const rebar = new THREE.Mesh(rebarGeom, matMetal);
  rebar.name = "basement_rebar_rod";
  rebar.position.set(13.12, elevAt(13.12, 6.02) + 0.028, 6.02);
  rebar.rotation.y = 0.46;
  buildingGroup.add(rebar);

  // Two dark sensor cables running from Manhole m3 toward bottom-right of cam5, raised above floor slope
  const cable1Curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(dX + 0.02, basementFloorY - 0.08, dZ + 0.15),
    new THREE.Vector3(dX + 0.05, elevAt(dX + 0.05, dZ + 0.29) + 0.025, dZ + 0.29),
    new THREE.Vector3(14.18, elevAt(14.18, 6.35) + 0.025, 6.35),
    new THREE.Vector3(14.23, elevAt(14.23, 7.15) + 0.03, 7.15)
  ]);
  const cable1Geom = new THREE.TubeGeometry(cable1Curve, 24, 0.009, 8, false);
  const cable1 = new THREE.Mesh(cable1Geom, matDarkHole);
  cable1.name = "sensor_cable_1";
  buildingGroup.add(cable1);

  const cable2Curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(dX + 0.14, basementFloorY - 0.08, dZ + 0.08),
    new THREE.Vector3(dX + 0.24, elevAt(dX + 0.24, dZ + 0.2) + 0.03, dZ + 0.2),
    new THREE.Vector3(14.42, elevAt(14.42, 6.25) + 0.025, 6.25),
    new THREE.Vector3(14.26, elevAt(14.26, 7.15) + 0.03, 7.15)
  ]);
  const cable2Geom = new THREE.TubeGeometry(cable2Curve, 24, 0.009, 8, false);
  const cable2 = new THREE.Mesh(cable2Geom, matDarkHole);
  cable2.name = "sensor_cable_2";
  buildingGroup.add(cable2);

  // Back wall on the right of the pillar (at z=2.90, x=14.55 to 18.00) with light baseboard & shutter slats (seen in cam5)
  addBox(
    "basement_back_wall_baseboard",
    14.55,
    17.85,
    basementFloorY + 0.35,
    basementFloorY + 0.55,
    2.9,
    2.98,
    matConcreteLight,
    buildingGroup
  );
  addBox(
    "basement_back_wall_vent",
    15.1,
    15.65,
    basementFloorY + 0.4,
    basementFloorY + 0.48,
    2.98,
    3.0,
    matWhite,
    buildingGroup
  );
  addBox(
    "basement_back_shutter",
    14.55,
    17.85,
    basementFloorY + 0.55,
    2.1,
    2.9,
    2.96,
    matShutter,
    buildingGroup
  );

  // Building outer/cutaway walls around Storage s6 & north corridor (cutaway roof so basement is visible)
  addBox("building_north_ corridor_wall", 7.45, 18.25, -0.56, 2.1, 2.65, 2.9, matConcrete, buildingGroup);
  addBox("building_east_wall", 18.0, 18.25, basementFloorY, 2.1, 0.25, 9.25, matConcrete, buildingGroup);
  addBox("building_south_wall", 7.45, 18.25, basementFloorY, 2.1, 9.0, 9.25, matConcrete, buildingGroup);
  addBox("basement_west_wall_upper", 11.2, 11.45, basementFloorY, 2.1, 2.9, 7.6, matConcrete, buildingGroup);

  // 9. Staircase leading from door_threshold_m (y = 0.80) down into Storage s6 (y = -0.56)
  const stairGroup = new THREE.Group();
  stairGroup.name = "staircase";
  root.add(stairGroup);

  // Staircase enclosure walls (x = 7.45 to 11.20, z = 6.45 to 9.00)
  addBox("staircase_north_wall", 7.45, 11.2, basementFloorY, 1.8, 6.45, 6.7, matConcrete, stairGroup);
  // Entrance threshold sill at site.door_threshold_m
  addBox(
    "door_threshold",
    7.45,
    8.85,
    basementFloorY,
    doorThresholdY,
    8.8,
    9.05,
    matConcreteLight,
    stairGroup
  );
  // Upper landing inside threshold
  addBox(
    "stair_upper_landing",
    7.45,
    8.85,
    basementFloorY,
    doorThresholdY,
    6.7,
    8.8,
    matConcrete,
    stairGroup
  );

  // 8 steps descending eastward from x = 8.85 (y = doorThresholdY) to x = 11.20 (y = basementFloorY)
  const numSteps = 8;
  const stepSpanX = (11.2 - 8.85) / numSteps;
  const stepRiseY = (doorThresholdY - basementFloorY) / numSteps;
  for (let i = 0; i < numSteps; i++) {
    const sx0 = 8.85 + i * stepSpanX;
    const sx1 = sx0 + stepSpanX;
    const sy1 = doorThresholdY - (i + 0.5) * stepRiseY;
    addBox(
      `stair_step_${i + 1}`,
      sx0,
      sx1,
      basementFloorY,
      sy1,
      6.7,
      9.0,
      matConcreteLight,
      stairGroup
    );
  }

  return {
    cameras: {
      cam1: {
        position: [14.6, 2.2, 21.1],
        lookAt: [9.8, 0.25, 21.2],
        fov: 60
      },
      cam5: {
        position: [13.95, basementFloorY + 1.2, 7.45],
        lookAt: [14.12, basementFloorY + 0.04, 5.25],
        fov: 44
      }
    },
    water: {
      pond: {
        outline: [
          [pondX0, pondZ0],
          [pondX0, pondZ1],
          [pondX1, pondZ1],
          [pondX1, pondZ0]
        ],
        base_y: pondBaseY
      },
      basement: {
        outline: [
          [bx0, bz0],
          [bx0, bz1],
          [bx1, bz1],
          [bx1, bz0]
        ],
        floor_y: basementFloorY,
        slope: basementSlope,
        drain_xz: [drainXZ[0], drainXZ[1]]
      },
      manhole_m2: {
        center: [m2Center[0], m2Center[1]],
        radius: m2Radius,
        base_y: m2BaseY
      }
    },
    materials: {
      water: {
        color: "#3a7bd5",
        opacity: 0.6
      }
    }
  };
}
