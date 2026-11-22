"""Run with python3 -m unittest discover -s tests."""
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from api import index as api


class ReservationTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.engine = create_engine("sqlite:///" + str(Path(folder.name) / "test.db"))
        self.addCleanup(self.engine.dispose)
        self.enterContext(patch.object(api, "engine", self.engine))
        self.enterContext(patch.dict(os.environ, PARKEASE_CAMERA_TOKEN="unit-test"))
        api.initialize()
        self.camera = api.app.test_client()
        self.users = [api.app.test_client(), api.app.test_client()]
        for i, client in enumerate(self.users):
            result = client.post("/api/signup", json={"username": f"driver{i}", "password":"long-test-password"})
            self.assertEqual(result.status_code, 200)
        self.revision = "a"*32
        self.data = {"revision":self.revision, "observed":time.time(), "aspect":1.5, "entrance":[.5,1],
                     "bays":[{"id":"A1","points":[[0,0],[.2,0],[.2,.2],[0,.2]],"occupied":False}]}
        self.payload = {"bay":"A1","revision":self.revision}
        self.assertEqual(self.publish(), 200)

    def publish(self):
        return self.camera.post("/api/telemetry", json=self.data, headers={"Authorization":"Bearer unit-test"}).status_code

    def test_competing_drivers_and_owner_cancellation(self):
        with ThreadPoolExecutor(2) as pool:
            codes = list(pool.map(lambda c:c.post("/api/book",json=self.payload).status_code, self.users))
        self.assertEqual(sorted(codes), [201,409])
        winner, loser = self.users[codes.index(201)], self.users[codes.index(409)]
        loser.post("/api/cancel",json={})
        self.assertEqual(winner.get("/api/state").json["mine"]["bay"], "A1")
        self.assertIsNone(loser.get("/api/state").json["mine"])
        winner.post("/api/cancel",json={})
        self.assertEqual(loser.post("/api/book",json=self.payload).status_code,201)

    def test_login_camera_and_staleness(self):
        self.assertEqual(self.camera.post("/api/book",json=self.payload).status_code,401)
        self.assertEqual(self.camera.post("/api/telemetry",json=self.data).status_code,403)
        self.assertEqual(self.publish(),409)
        self.data.update(observed=time.time(), bays=[dict(self.data["bays"][0],occupied=True)])
        self.assertEqual(self.publish(),200)
        self.assertEqual(self.users[0].post("/api/book",json=self.payload).status_code,409)
        self.data.update(observed=time.time(), bays=[dict(self.data["bays"][0],occupied=False)])
        self.assertEqual(self.publish(),200)
        with patch.object(api.time,"time",return_value=time.time()+25):
            self.assertFalse(self.camera.get("/api/state").json["fresh"])
            self.assertEqual(self.users[0].post("/api/book",json=self.payload).status_code,409)
        self.users[0].post("/api/logout",json={})
        self.assertEqual(self.users[0].post("/api/book",json=self.payload).status_code,401)
        self.assertEqual(self.users[0].post("/api/login",json={"username":"driver0","password":"long-test-password"}).status_code,200)
