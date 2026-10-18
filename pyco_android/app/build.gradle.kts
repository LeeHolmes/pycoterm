import java.net.HttpURLConnection
import java.net.URI
import java.nio.file.Files
import java.nio.file.StandardCopyOption

fun downloadFile(sourceUrl: String, destination: File, accept: String) {
    val temporary = destination.resolveSibling("${destination.name}.tmp")
    destination.parentFile.mkdirs()

    val connection = URI(sourceUrl).toURL().openConnection() as HttpURLConnection
    connection.connectTimeout = 10_000
    connection.readTimeout = 30_000
    connection.setRequestProperty("Accept", accept)
    try {
        val status = connection.responseCode
        if (status !in 200..299) {
            throw GradleException("Unable to download $sourceUrl: HTTP $status")
        }
        connection.inputStream.use { input ->
            Files.copy(input, temporary.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
        if (temporary.length() == 0L) {
            throw GradleException("Downloaded file is empty: $sourceUrl")
        }
        Files.move(
            temporary.toPath(),
            destination.toPath(),
            StandardCopyOption.REPLACE_EXISTING,
        )
    } finally {
        temporary.delete()
        connection.disconnect()
    }
}

plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

val generatedPythonDir = layout.buildDirectory.dir("generated/python/main")
val generatedAssetsDir = layout.buildDirectory.dir("generated/assets/main")

android {
    namespace = "com.leeholmes.pyco"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.leeholmes.pyco"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    sourceSets {
        getByName("main") {
            // Package the canonical web UI directly. No Android-side copy can drift.
            assets.srcDir("../../pyco_web")
            assets.srcDir(generatedAssetsDir)
        }
    }
}

chaquopy {
    sourceSets {
        getByName("main") {
            srcDir(generatedPythonDir)
        }
    }
    defaultConfig {
        version = "3.13"
        pip {
            install("Pygments==2.19.2")
        }
    }
}

val syncLauncherIcon by tasks.registering(Copy::class) {
    from("../../pyco_web/icons/icon-512.png")
    into("src/main/res/drawable-nodpi")
    rename { "ic_launcher.png" }
}

val syncMarkdownRenderer by tasks.registering(Copy::class) {
    from("../../markdown_renderer.py")
    into(generatedPythonDir)
}

val downloadPycoContent by tasks.registering {
    val sourceRoot = "https://raw.githubusercontent.com/LeeHolmes/pyco/main"
    val pycoFile = generatedPythonDir.map { it.file("pyco.py") }
    val pycoAsset = generatedAssetsDir.map { it.file("pyco.py") }
    val readmeFile = generatedAssetsDir.map { it.file("PYCO_README.md") }
    outputs.files(pycoFile, pycoAsset, readmeFile)
    outputs.upToDateWhen { false }

    doLast {
        downloadFile(
            "$sourceRoot/pyco.py",
            pycoFile.get().asFile,
            "text/x-python,text/plain",
        )
        pycoAsset.get().asFile.parentFile.mkdirs()
        pycoFile.get().asFile.copyTo(pycoAsset.get().asFile, overwrite = true)
        val readme = readmeFile.get().asFile
        downloadFile("$sourceRoot/README.md", readme, "text/markdown,text/plain")
    }
}

tasks.named("preBuild") {
    dependsOn(downloadPycoContent, syncLauncherIcon, syncMarkdownRenderer)
}

tasks.matching {
    it.name.startsWith("merge") && it.name.endsWith("PythonSources")
}.configureEach {
    dependsOn(downloadPycoContent, syncMarkdownRenderer)
}
