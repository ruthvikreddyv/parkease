# ParkEase

[Open the ParkEase demo](https://parkease-demo-iota.vercel.app/)

Explore ten parking bays from the original ParkEase camera project. Search by bay label or occupancy, simulate an arrival or departure, and see the nearest available space update. Restore the snapshot to return to the detector output. Live CCTV monitoring and account-backed reservations are described below.

## Run the public dashboard

```sh
python3 -m http.server 8000 --directory public
```

Open http://localhost:8000. This static-only command runs the saved simulation. Use the API setup below for real accounts and reservations.

## Reproduce the detector snapshot

Use Python 3.11 or newer. The original camera workflow uses OpenCV windows and requires a local camera. Snapshot generation only needs the bundled classifier, labelled coordinates and saved bay crops.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r vision/requirements.txt
cd vision
python3 export_snapshot.py
```

The detector scans each crop using the original cascade parameters. The recommendation uses Euclidean distance between the entrance centre and available bay centres. The saved crops produce eight available bays and two occupied bays. B2 is the closest available space.

For the local camera interface, run `python3 main.py` from the vision directory with a camera available at OpenCV index 2. The original capture and calibration tools are included there.

[Original ParkEase project and demonstration recording](https://github.com/ruthvikreddyv/parkeasee/tree/fe30b60c9e8d86d81a661445b66cc047dfb26aa0)

## Live CCTV and driver reservations

The CCTV worker runs beside the camera or NVR. Drivers use the web dashboard. The worker sends normalized bay outlines, boolean occupancy and timestamps over HTTPS. The camera URL and video stay on the operator machine. The original simulation is available separately and cannot create a reservation.

### Start a local installation

Use Python 3.11 or newer, from the repository root.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt -r vision/requirements.txt
export PARKEASE_CAMERA_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 api/index.py
```

This initializes a local SQLite database and serves the dashboard at http://127.0.0.1:8000. Keep the terminal running. In a second terminal activate the same environment, set the same camera token, set PARKEASE_SERVER to the dashboard URL, and set PARKEASE_CAMERA_SOURCE to your RTSP/HTTP stream, camera index or video file. For credentialed streams, set that variable privately on the camera machine.

```sh
python3 vision/cctv.py calibrate --layout camera-layout.json
python3 vision/cctv.py monitor --layout camera-layout.json
```

In the calibration window click four corners per bay, or press **A** on an empty layout to propose bays from visible painted outlines. Click inside an existing bay to select it, drag its corners to refine it, or press **D** to remove it. **U** removes the last unfinished point. **E** followed by a click sets the entrance. **S** saves the reviewed layout and **Esc** discards unsaved changes. Recalibrate if the camera moves. Automatic proposals work best on clearly outlined bays and need a visual check.

Monitoring samples approximately once per second and takes the majority of three detections for each bay. The detector reuses the original vehicle cascade. Occlusion, viewing angle and lighting affect its accuracy. Validate detections with labelled footage from the actual camera before using it for operations.

### Hosted installation

Set PARKEASE_DATABASE_URL to a dedicated PostgreSQL connection with TLS and PARKEASE_CAMERA_TOKEN to a long random secret in the Vercel production environment. Use the same camera token on the worker. With the production database URL available in a trusted shell, initialize the ParkEase tables (rerun after updating an existing installation to add the driver profile table):

```sh
python3 -c 'from api.index import initialize; initialize()'
```

Redeploy after configuring the environment. Vercel serves the dashboard and Flask API; a persistent computer on the camera network runs the monitoring process. A hosted installation without a database reports offline and blocks account and booking writes.

New drivers enter their full name, contact number and username, then enter and confirm their password. Existing drivers keep their username and password and log in with an HTTP-only session cookie. Each driver may hold one bay for 15 minutes and may cancel it. A bay can have only one active reservation. The server checks login, occupancy, camera layout revision and telemetry freshness in the booking transaction. Observations older than 20 seconds pause bookings. Existing holds survive camera outages. Layout revisions with active holds are rejected until the holds expire or are cancelled.
