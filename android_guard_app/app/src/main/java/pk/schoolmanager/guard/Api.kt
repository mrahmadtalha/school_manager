package pk.schoolmanager.guard

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.SystemClock
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

class ApiException(val kind: Kind, message: String) : Exception(message) {
    enum class Kind { NETWORK, AUTH, SERVER }
}

/** android.org.json turns a JSON null into the text "null"; this returns "" instead. */
fun JSONObject.str(name: String): String = if (isNull(name)) "" else optString(name, "")

/** Keeps the session cookie the server gives at sign-in (in memory only). */
private class MemoryCookieJar : CookieJar {
    private val store = HashMap<String, MutableList<Cookie>>()

    @Synchronized
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        val list = store.getOrPut(url.host) { mutableListOf() }
        list.removeAll { old -> cookies.any { it.name == old.name } }
        list.addAll(cookies)
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val now = System.currentTimeMillis()
        return store[url.host]?.filter { it.expiresAt > now } ?: emptyList()
    }

    @Synchronized
    fun clear() {
        store.clear()
    }
}

/** What the connection QR code on the school computer says. */
data class PairCode(val addresses: List<String>, val token: String)

/** Reads the text of a connection QR code ("SMGUARD1|address,address|token"), or null. */
fun parsePairCode(text: String): PairCode? {
    val parts = text.trim().split("|")
    if (parts.size != 3 || parts[0] != "SMGUARD1") return null
    val addresses = parts[1].split(",").map { it.trim() }.filter { it.isNotEmpty() }
    val token = parts[2].trim()
    if (addresses.isEmpty() || token.isEmpty()) return null
    return PairCode(addresses, token)
}

/** All talking to the School Manager server (JSON over plain http on the school network). */
object Api {
    private val jar = MemoryCookieJar()
    private val client = OkHttpClient.Builder()
        .cookieJar(jar)
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    private const val DISCOVERY_PORT = 50555
    private const val DISCOVERY_REQUEST = "SMGUARD_WHERE_ARE_YOU"
    private const val DISCOVERY_APP = "school_manager_guard"

    private var baseUrl = ""
    private var username = ""
    private var password = ""
    private var token = ""          // device token given when the phone was connected

    fun normalizeBase(input: String): String {
        var text = input.trim().trimEnd('/')
        if (text.isEmpty()) return ""
        if (!text.startsWith("http://") && !text.startsWith("https://")) text = "http://$text"
        return text
    }

    /** Loads the saved connection after the app process was restarted. */
    @Synchronized
    fun restore(prefs: Prefs) {
        if (baseUrl.isNotBlank()) return
        baseUrl = normalizeBase(prefs.server)
        username = prefs.username
        password = prefs.password
        token = prefs.deviceToken
    }

    /** The server address in use now (it can change when the computer is found again). */
    @Synchronized
    fun server(): String = baseUrl

    /** The device token to keep on the phone, or "" with an older server. */
    @Synchronized
    fun deviceToken(): String = token

    /** Sign in by typing the address, username and password. */
    @Synchronized
    fun login(server: String, user: String, pass: String): JSONObject {
        jar.clear()
        baseUrl = normalizeBase(server)
        username = user
        password = pass
        token = ""
        return doLogin()
    }

    /** Sign in again at [server] with what is already known (used when the computer's address changed). */
    @Synchronized
    fun reconnect(server: String): JSONObject {
        jar.clear()
        baseUrl = normalizeBase(server)
        return doLogin()
    }

    /** Connect with the code shown on the computer. Tries each address in the code until one answers. */
    @Synchronized
    fun pair(addresses: List<String>, pairToken: String): JSONObject {
        var lastError: ApiException? = null
        for (address in addresses) {
            val base = normalizeBase(address)
            if (base.isEmpty()) continue
            jar.clear()
            baseUrl = base
            try {
                val (code, json) = post("/api/qr/pair", JSONObject().put("pair_token", pairToken))
                if (code == 200 && json.optBoolean("ok")) {
                    token = json.str("device_token")
                    username = ""
                    password = ""
                    json.put("server", base)
                    return json
                }
                val message = json.str("message").ifBlank { "Connection failed (HTTP $code)." }
                throw ApiException(ApiException.Kind.AUTH, message)
            } catch (e: ApiException) {
                if (e.kind == ApiException.Kind.AUTH) throw e
                lastError = e                         // nothing answered here: try the next address
            }
        }
        throw lastError ?: ApiException(ApiException.Kind.NETWORK, "Cannot reach the school computer.")
    }

    private fun failure(code: Int, json: JSONObject): ApiException {
        val message = json.str("message").ifBlank { "Sign-in failed (HTTP $code)." }
        val kind = if (code in listOf(400, 401, 403, 429)) ApiException.Kind.AUTH else ApiException.Kind.SERVER
        return ApiException(kind, message)
    }

    private fun doLogin(): JSONObject {
        if (token.isNotBlank()) {
            val (code, json) = post("/api/qr/login", JSONObject().put("device_token", token))
            if (code == 200 && json.optBoolean("ok")) return json
            if (username.isBlank() || password.isBlank()) throw failure(code, json)
            // the token no longer works: try the typed password below
        }
        val body = JSONObject().put("username", username).put("password", password)
        val (code, json) = post("/api/qr/login", body)
        if (code == 200 && json.optBoolean("ok")) {
            val given = json.str("device_token")
            if (given.isNotBlank()) token = given
            return json
        }
        throw failure(code, json)
    }

    /**
     * Asks the Wi-Fi "where is School Manager?" and returns the addresses that answered
     * (normally one). Works when the computer's address has changed.
     */
    fun discover(timeoutMs: Int = 3000): List<String> {
        val found = ArrayList<String>()
        val socket = try {
            DatagramSocket()
        } catch (e: Exception) {
            return found
        }
        try {
            socket.broadcast = true
            socket.soTimeout = 600
            val request = DISCOVERY_REQUEST.toByteArray(Charsets.UTF_8)
            val targets = broadcastTargets()
            val buffer = ByteArray(256)
            val deadline = SystemClock.elapsedRealtime() + timeoutMs
            while (found.isEmpty() && SystemClock.elapsedRealtime() < deadline) {
                for (target in targets) {
                    try {
                        socket.send(DatagramPacket(request, request.size, target, DISCOVERY_PORT))
                    } catch (e: IOException) {
                        // that network cannot broadcast; the others may
                    }
                }
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)
                    val json = JSONObject(String(packet.data, 0, packet.length, Charsets.UTF_8))
                    val port = json.optInt("port", 0)
                    val host = packet.address?.hostAddress
                    if (json.optString("app") == DISCOVERY_APP && port > 0 && host != null) {
                        found.add("http://$host:$port")
                    }
                } catch (e: SocketTimeoutException) {
                    // nobody answered yet: ask again
                } catch (e: JSONException) {
                    // some other device answered: ignore it
                }
            }
        } catch (e: Exception) {
            // no answer is not an error, the caller just shows "not connected"
        } finally {
            socket.close()
        }
        return found
    }

    private fun broadcastTargets(): List<InetAddress> {
        val targets = ArrayList<InetAddress>()
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces != null && interfaces.hasMoreElements()) {
                val nic = interfaces.nextElement()
                if (!nic.isUp || nic.isLoopback) continue
                for (address in nic.interfaceAddresses) {
                    val broadcast = address.broadcast
                    if (broadcast != null && !targets.contains(broadcast)) targets.add(broadcast)
                }
            }
        } catch (e: Exception) {
            // fall back to the general broadcast address below
        }
        try {
            targets.add(InetAddress.getByName("255.255.255.255"))
        } catch (e: Exception) {
            // nothing more to try
        }
        return targets
    }

    /** Sends one scanned QR text to the server and returns its answer. */
    @Synchronized
    fun scan(token: String): JSONObject {
        val body = JSONObject().put("token", token)
        var answer = post("/api/qr/scan", body)
        if (answer.first == 401) {            // session expired: sign in again, once
            doLogin()
            answer = post("/api/qr/scan", body)
        }
        if (answer.first == 200 || answer.first == 400) return answer.second
        throw ApiException(
            ApiException.Kind.SERVER,
            answer.second.str("message").ifBlank { "Server error (HTTP ${answer.first})." }
        )
    }

    /** Today's numbers and the school name (also proves the connection still works). */
    @Synchronized
    fun ping(): JSONObject {
        var answer = get("/api/qr/ping")
        if (answer.first == 401) {
            doLogin()
            answer = get("/api/qr/ping")
        }
        if (answer.first == 200) return answer.second
        throw ApiException(ApiException.Kind.SERVER, "Server error (HTTP ${answer.first}).")
    }

    /** The student's photo, or null when there is none or it cannot be loaded. */
    fun photo(path: String): Bitmap? {
        if (path.isBlank()) return null
        return try {
            val request = newRequest(path).get().build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    null
                } else {
                    response.body?.bytes()?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                }
            }
        } catch (e: Exception) {
            null
        }
    }

    private fun newRequest(path: String): Request.Builder {
        try {
            return Request.Builder().url(baseUrl + path)
        } catch (e: IllegalArgumentException) {
            throw ApiException(ApiException.Kind.NETWORK, "The server address is not valid.")
        }
    }

    private fun post(path: String, body: JSONObject): Pair<Int, JSONObject> {
        val request = newRequest(path).post(body.toString().toRequestBody(jsonType)).build()
        return execute(request)
    }

    private fun get(path: String): Pair<Int, JSONObject> = execute(newRequest(path).get().build())

    private fun execute(request: Request): Pair<Int, JSONObject> {
        val reply: Pair<Int, String> = try {
            client.newCall(request).execute().use { Pair(it.code, it.body?.string() ?: "") }
        } catch (e: IOException) {
            throw ApiException(ApiException.Kind.NETWORK, "Cannot reach the school computer.")
        }
        val json = try {
            JSONObject(reply.second)
        } catch (e: JSONException) {
            throw ApiException(
                ApiException.Kind.SERVER,
                "Unexpected reply from the server (HTTP ${reply.first}). Check the address and port."
            )
        }
        return Pair(reply.first, json)
    }
}
