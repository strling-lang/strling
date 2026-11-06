import org.gradle.api.publish.maven.MavenPublication

plugins {
    kotlin("jvm") version "2.0.20"
    `java-library`
    id("maven-publish")
}

group = "com.strling"
val productVersion = "4.0.0"
require(providers.gradleProperty("version").orElse(productVersion).get() == productVersion) {
    "Release version override must equal the governed product coordinate"
}
version = productVersion

repositories {
    providers.environmentVariable("STRLING_MAVEN_REPOSITORY").orNull?.let {
        maven { url = uri(it) }
    }
    mavenLocal()
    mavenCentral()
}

dependencies {
    api("com.strling:strling-jvm:4.0.0") { version { strictly(productVersion) } }
    testImplementation(platform("org.junit:junit-bom:5.10.1"))
    testImplementation(kotlin("test"))
}

dependencyLocking {
    lockAllConfigurations()
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
    addTestListener(object : org.gradle.api.tasks.testing.TestListener {
        override fun beforeSuite(suite: org.gradle.api.tasks.testing.TestDescriptor) {}
        override fun afterSuite(suite: org.gradle.api.tasks.testing.TestDescriptor, result: org.gradle.api.tasks.testing.TestResult) {
            if (suite.parent == null) {
                println("[STRling Audit] Tests: ${result.testCount}, Skipped: ${result.skippedTestCount}")
            }
        }
        override fun beforeTest(testDescriptor: org.gradle.api.tasks.testing.TestDescriptor) {}
        override fun afterTest(testDescriptor: org.gradle.api.tasks.testing.TestDescriptor, result: org.gradle.api.tasks.testing.TestResult) {}
    })
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_11)
        allWarningsAsErrors = true
    }
}

publishing {
    repositories {
        providers.environmentVariable("STRLING_LOCAL_MAVEN_REPOSITORY").orNull?.let {
            maven {
                name = "localInstall"
                url = uri(it)
            }
        }
    }
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            pom {
                name.set("STRling Kotlin adapter")
                description.set("Thin Kotlin adapter for the canonical STRling compiler")
                url.set("https://github.com/strling-lang/strling")
                licenses { license { name.set("Apache License 2.0"); url.set("https://www.apache.org/licenses/LICENSE-2.0") } }
                developers { developer { id.set("strling-lang"); name.set("STRling Team") } }
                scm {
                    connection.set("scm:git:https://github.com/strling-lang/strling.git")
                    developerConnection.set("scm:git:ssh://git@github.com/strling-lang/strling.git")
                    url.set("https://github.com/strling-lang/strling")
                    tag.set("v$version")
                }
            }
        }
    }
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.jar { from(rootProject.file("../../LICENSE")) { into("META-INF") } }
