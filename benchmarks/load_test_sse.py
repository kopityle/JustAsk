# Запуск:
# locust -f benchmarks/load_test_sse.py --host http://localhost:8000
# HTML: --html=benchmarks/results/locust_<timestamp>.html
import os
import time, json, httpx
from locust import HttpUser, task, between

class JustAskStudentUser(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        # Переиспользуем клиент для предотвращения утечки сокетов
        self.client_http = httpx.Client(timeout=60.0)
        token = os.getenv("TEST_STUDENT_JWT_TOKEN", "").strip()
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def on_stop(self):
        self.client_http.close()

    @task(3)
    def ask_valid_question(self):
        # Учебный вопрос: должен пройти dense-поиск и вызвать LLM
        payload = {"question": "Что называется первичным ключом и составным первичным ключом?"}
        start_time = time.perf_counter()
        ttft = None
        total_tokens = 0

        try:
            with self.client_http.stream("POST", f"{self.host}/api/chat/stream", json=payload, headers=self.headers) as response:
                if response.status_code != 200:
                    self.environment.events.request.fire(
                        request_type="SSE_STREAM", name="/api/chat/stream",
                        response_time=(time.perf_counter() - start_time) * 1000,
                        response_length=0, exception=Exception(f"HTTP {response.status_code}")
                    )
                    return

                for line in response.iter_lines():
                    if line.startswith("data: ") and not line.endswith("[DONE]"):
                        data_str = line.replace("data: ", "").strip()
                        try:
                            data_json = json.loads(data_str)
                            if data_json.get("type") == "token" and ttft is None:
                                ttft = (time.perf_counter() - start_time) * 1000
                                self.environment.events.request.fire(
                                    request_type="TTFT", name="Time_To_First_Token",
                                    response_time=ttft, response_length=0, exception=None
                                )
                            total_tokens += 1
                        except Exception:
                            pass

            total_duration = (time.perf_counter() - start_time) * 1000
            self.environment.events.request.fire(
                request_type="SSE_STREAM", name="/api/chat/stream",
                response_time=total_duration, response_length=total_tokens, exception=None
            )
        except Exception as e:
            self.environment.events.request.fire(
                request_type="SSE_STREAM", name="/api/chat/stream",
                response_time=(time.perf_counter() - start_time) * 1000,
                response_length=0, exception=e
            )

    @task(1)
    def ask_offtopic_question(self):
        # Fast-Fail тест
        payload = {"question": "Как сварить борщ на Марсе?"}
        start_time = time.perf_counter()
        with self.client_http.stream("POST", f"{self.host}/api/chat/stream", json=payload, headers=self.headers) as response:
            content = response.read().decode("utf-8")
            duration = (time.perf_counter() - start_time) * 1000
            
            # Проверяем, что ответ действительно содержит отказ и вернулся быстрее 500мс
            assert '"is_found": false' in content, "Fast-fail не сработал на оффтоп!"
            assert duration < 500, f"Fast-fail слишком медленный: {duration}ms"
            
            self.environment.events.request.fire(
                request_type="FAST_FAIL", name="Fast_Fail_Offtopic",
                response_time=duration, response_length=len(content), exception=None
            )
