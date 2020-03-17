from openlibrary.core.init import Init

class TestService:
    def create_service(self, name, config):
        config2 = {
            name: config
        }
        return Init(config2).services[name]


    def test_stdout(self, tmpdir):
        s = self.create_service("echo", {
            "command": "echo hello",
            "stdout": tmpdir.join("echo.txt").strpath,
            "stderr": tmpdir.join("echo.log").strpath
        })

        s.start().wait()
        assert tmpdir.join("echo.txt").read().strip() == "hello"

    def test_change_root(self, tmpdir):
        s = self.create_service("pwd", {
            "command": "pwd",
            "root": tmpdir.strpath,
            "stdout": tmpdir.join("pwd.txt").strpath,
            "stderr": tmpdir.join("pwd.log").strpath
        })

        s.start().wait()
        assert tmpdir.join("pwd.txt").read().strip() == tmpdir.strpath

    def test_poll_and_wait(self, tmpdir):
        s = self.create_service("sleep", {
            "command": "sleep 0.2",
            "stdout": tmpdir.join("sleep.txt").strpath,
            "stderr": tmpdir.join("sleep.log").strpath
        })
        s.start()
        assert s.poll() is None
        assert s.wait() == 0
        assert s.poll() == 0

    def test_stop(self, tmpdir):
        s = self.create_service("sleep", {
            "command": "sleep 100",
            "stdout": tmpdir.join("sleep.txt").strpath,
            "stderr": tmpdir.join("sleep.log").strpath
        })
        s.start()
        assert s.is_alive() is True
        s.stop(timeout=0.2)
        assert s.is_alive() is False
