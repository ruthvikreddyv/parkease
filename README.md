# ParkEase

[Open the ParkEase demo](https://parkease-demo-iota.vercel.app/)

Explore ten parking bays from the original ParkEase camera project. Search by bay label or occupancy, simulate an arrival or departure, and see the nearest available space update. Restore the snapshot to return to the detector output. The login and signup pages create a fictional driver session in the current tab.

## Run the public dashboard

```sh
python3 -m http.server 8000 --directory public
```

Open http://localhost:8000. Vercel serves the public directory as a static site. The dashboard uses saved observations. Visitors cannot reserve a real parking space.

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
