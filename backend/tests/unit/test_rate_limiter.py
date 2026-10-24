from app.services.limits import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_and_then_says_how_long_to_wait() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock)

    assert [limiter.hit("ip", 3, 60) for _ in range(3)] == [None, None, None]
    clock.now += 20
    assert limiter.hit("ip", 3, 60) == 40  # el primero sale de la ventana en 40 s


def test_window_slides_instead_of_resetting_each_minute() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("ip", 2, 60)
    clock.now += 50
    limiter.hit("ip", 2, 60)

    clock.now += 15  # 65 s después del primero: solo ha caducado uno
    assert limiter.hit("ip", 2, 60) is None
    assert limiter.hit("ip", 2, 60) is not None


def test_keys_are_independent() -> None:
    limiter = SlidingWindowLimiter(FakeClock())
    limiter.hit("a", 1, 60)

    assert limiter.hit("a", 1, 60) is not None
    assert limiter.hit("b", 1, 60) is None


def test_rejected_attempts_do_not_extend_the_wait() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("ip", 1, 60)
    for _ in range(5):
        limiter.hit("ip", 1, 60)

    clock.now += 60
    assert limiter.hit("ip", 1, 60) is None


def test_idle_keys_are_forgotten() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock)
    limiter.SWEEP_EVERY = 3
    limiter.hit("vieja", 5, 60)
    clock.now += 61
    limiter.hit("nueva", 5, 60)
    limiter.hit("nueva", 5, 60)  # tercer evento: limpieza

    assert set(limiter._events) == {"nueva"}
