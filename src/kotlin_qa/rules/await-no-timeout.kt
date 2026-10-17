import com.google.android.gms.tasks.Tasks
import java.util.concurrent.TimeUnit

fun waits(task: com.google.android.gms.tasks.Task<String>) {
    // ruleid: kqaci.kt.await-no-timeout
    Tasks.await(task)
    // ok: kqaci.kt.await-no-timeout
    Tasks.await(task, 60, TimeUnit.SECONDS)
}
