# Backflow: 1-minute video script

About 200 words, for a fast speaker. Record it at your own pace; the video gets re-timed to your voice afterwards.

**Cameras**
This is a real flood test site in Switzerland: a pond, channels, drain pipes and a building. Researchers flood it on purpose and film it from several cameras.

**The problem** (still over the cameras and the drawing)
Engineers predict floods with drainage simulations. But some of their settings can't be measured, so they're guessed. Checking those guesses needs water sensors underground, which almost nobody has. Video is everywhere.

**Argon builds the site**
We gave Gemini 4 Argon the site's engineering drawing. It built the whole site in 3D, compared it with the real camera, spotted a missing drain, and fixed its own code.

**Managed Agents**
Then Managed Agents each test one theory of how the water gets into the building, running the simulation in their own cloud sandbox.

**The core loop**
Now the core loop. The simulation predicts the flood three ways: A, B and C. Each one is drawn in Argon's 3D site, from the real camera's angle, right next to the real footage. Argon watches the whole flood, picks the version closest to reality, and says what's still off. The settings move toward its pick, and it goes again. Only video. No sensors.

**The test**
Then the real test: a different flood the model has never seen. After Argon watched just one flood, the prediction became more than five times more accurate. That's in the same range researchers get by tuning with water sensors.

**End**
That means any city with a street camera or a phone video of a flood could check its flood model before spending millions on new drains. This is Backflow, built with Gemini 4 Argon and Managed Agents.
