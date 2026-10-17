fun hold(lock: android.os.PowerManager.WakeLock) {
    // ruleid: kqaci.kt.wakelock-no-timeout
    lock.acquire()
    // ok: kqaci.kt.wakelock-no-timeout
    lock.acquire(10 * 60 * 1000L)
}
