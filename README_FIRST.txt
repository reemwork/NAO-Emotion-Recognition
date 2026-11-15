NAO ONE-CLICK STARTUP + SAVED IP

1. Back up your existing START_NAO.ps1 and START_NAO.bat first.
2. Copy START_NAO.bat, START_NAO.ps1, nao_connection.json to the root of
   C:\Users\reema\Desktop\NAO-Emotion-Recognition (beside backend and run_session.py).
3. After the robot is free and powered on, double-click START_NAO.bat.
4. It checks the saved robot IP on SSH port 22 and tries nao.local resolution.
   If both fail, enter the NAO IP shown in Choregraphe; successful sessions
   save the address in nao_connection.json for the next run.
5. It starts Ollama and FastAPI if needed, checks qwen2.5vl:3b, and invokes
   the EXISTING run_session.py to perform the real robot session.

No campus subnet scan. Robot is NOT automatically detected on networks
where nao.local does not resolve; you may need the current IP once.
A reachable SSH port does not guarantee SSH credentials/NAOqi work.
First run requires already installed packages, venv, working SSH keys,
NAOqi on robot, and configured scenarios/assets.

The IP is only persisted AFTER run_session.py returns success.
Don't start this while someone else is using the NAO robot.
Please review START_NAO.ps1 before running; the full physical flow has
NOT been tested here.

Git: nao_connection.json contains a local IP address and can stay local.
