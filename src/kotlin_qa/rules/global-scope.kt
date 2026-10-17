import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.launch

class Owner(private val scope: kotlinx.coroutines.CoroutineScope) {
    fun start() {
        // ruleid: kqaci.kt.global-scope
        GlobalScope.launch { work() }
        // ok: kqaci.kt.global-scope
        scope.launch { work() }
    }

    private fun work() = Unit
}
