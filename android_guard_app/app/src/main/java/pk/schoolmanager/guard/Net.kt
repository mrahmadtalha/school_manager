package pk.schoolmanager.guard

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/** Wi-Fi helpers. */
object Net {

    private fun manager(context: Context): ConnectivityManager? =
        context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager

    @Suppress("DEPRECATION")
    private fun wifiNetworks(cm: ConnectivityManager) = cm.allNetworks.filter {
        cm.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
    }

    /** True when the phone is joined to a Wi-Fi network. */
    fun isWifiConnected(context: Context): Boolean {
        val cm = manager(context) ?: return false
        return try {
            wifiNetworks(cm).isNotEmpty()
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Sends this app's traffic over Wi-Fi even when that Wi-Fi has no internet.
     * A school Wi-Fi often has none, and then Android would otherwise try to
     * reach the school computer through mobile data and fail.
     */
    fun useWifi(context: Context) {
        val cm = manager(context) ?: return
        try {
            cm.bindProcessToNetwork(wifiNetworks(cm).firstOrNull())   // null = default network (e.g. a hotspot)
        } catch (e: Exception) {
            // keep the default network
        }
    }
}
