# busybar-apps-dev

My own BUSY Bar apps. Registered in busybar-manager via `appsDirs`.

Each app is a folder under `apps/`:

    apps/<slug>/
      app.py          # takes --host; argparse options become dashboard controls
      manifest.yaml   # name, description, tags
      requirements.txt  # optional (manager builds a .venv per app)

Start from `apps/hello-bar`. Test without hardware via busybar-emulator (Bar host 127.0.0.1:8080).
Windows: set BUSYBAR_PYTHON=python before starting the manager.
