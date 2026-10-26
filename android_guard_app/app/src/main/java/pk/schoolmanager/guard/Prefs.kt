package pk.schoolmanager.guard

import android.content.Context

/** Remembers the server address and the guard's sign-in on this phone. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("guard", Context.MODE_PRIVATE)

    var server: String
        get() = sp.getString("server", "") ?: ""
        set(value) = sp.edit().putString("server", value).apply()

    var username: String
        get() = sp.getString("username", "") ?: ""
        set(value) = sp.edit().putString("username", value).apply()

    /** Only used when the phone was connected by typing (older servers). */
    var password: String
        get() = sp.getString("password", "") ?: ""
        set(value) = sp.edit().putString("password", value).apply()

    /** Given by the computer when the phone is connected; replaces the password. */
    var deviceToken: String
        get() = sp.getString("device_token", "") ?: ""
        set(value) = sp.edit().putString("device_token", value).apply()

    fun isComplete(): Boolean =
        server.isNotBlank() &&
            (deviceToken.isNotBlank() || (username.isNotBlank() && password.isNotBlank()))

    /** Forget everything (used before connecting to another computer). */
    fun clearConnection() {
        sp.edit().remove("device_token").remove("password").apply()
    }
}
