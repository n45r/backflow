# Backflow: 1-minute video script

Timed to `runs/submission/backflow_v4_for_voiceover.mp4` (57 s). Written for a fast speaker.

**0:00 – 0:06** (cameras, site plan)
Cities plan their drains with flood simulations. But checking them needs sensors in the sewer, which almost nobody has. Floods get filmed all the time.

**0:06 – 0:14** (3D site, drain fix)
Gemini 4 Argon read the site plan and built the whole site in 3D. Comparing it with the camera, it spotted a missing drain and fixed its own code.

**0:14 – 0:20** (Managed Agents)
Three Managed Agents each take one theory of how the water gets in, and tune the simulation for it in their own cloud sandbox.

**0:20 – 0:35** (the core loop)
Now the core loop. A drainage simulation makes three versions of the flood: A, B and C. Each is drawn in Argon's 3D scene from the real camera's angle, and stitched beside the real footage. Argon watches the whole flood, picks the closest, and says what's still wrong. The settings move toward its pick, and it repeats. Only video. No sensors.

**0:35 – 0:51** (the test)
Then we freeze the model and test it on a different flood it has never seen. Before tuning, it was off by 34 millimetres of water. After watching one flood, it's off by 6, and the peak is within 5 millimetres. That's within the range of the original researchers, who tuned with sewer sensors.

**0:51 – 0:57** (end)
Backflow. Flood video in, a checked flood model out. Built with Gemini 4 Argon and Managed Agents.
