fun swallow() {
    // ruleid: kqaci.kt.empty-catch
    try {
        risky()
    } catch (e: Exception) {
    }
    // ok: kqaci.kt.empty-catch
    try {
        risky()
    } catch (e: Exception) {
        report(e)
    }
}

fun risky() = Unit

fun report(e: Exception) = Unit
