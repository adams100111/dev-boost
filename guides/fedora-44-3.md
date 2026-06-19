[00:00:00]  
**Introduction and Overview**  
- The video presents Fedora Linux 44 Workstation edition, focusing on installation and post-installation setup to optimize daily Linux use.  
- The host plans to guide viewers through creating bootable media from a Fedora 44 ISO, installing Fedora, and performing essential configurations to make the system fully usable.

[00:00:25]  
**Downloading Fedora 44 ISO and Creating Bootable Media**  
- Start from Windows and download the Fedora 44 Live ISO from the official Fedora Project website: **fedoraproject.org** → Download Fedora → Fedora Workstation ISO (supports Intel and AMD CPUs).  
- Tools for writing the ISO to USB/pen drive include:  
  - **Balena Etcher** (works on Windows, Mac, Linux): recommended for flashing the Fedora ISO.  
  - Rufus and Fedora Media Writer (uncertainty if Fedora Media Writer supports Windows, but stated to be compatible).  
- The flashing steps include selecting the ISO file, choosing the target USB or SSD drive, and flashing the image.  
- The host uses a scratch SSD for testing.

[00:02:38]  
**Booting and Installing Fedora Linux 44**  
- Boot from the prepared USB/SSD live media.  
- Initial welcome screen: "Welcome to Fedora Linux" (live session).  
- Begin installation by selecting "Install Fedora Linux."  
- Language selection and keyboard layout defaults to US English.  
- Disk partitioning choices include:  
  - Using the entire disk (removes all existing partitions, including other OSes).  
  - Sharing disk with other OSes or advanced manual setup with GParted.  
- The host chooses "use the entire disk" on a 1TB Toshiba hard drive without encryption.  
- Installation proceeds by deleting existing data and installing Fedora Linux 44 GNOME workstation edition.  
- After installation, users can reboot or exit to live desktop; reboot is recommended.

[00:05:01]  
**First Boot and Initial Setup**  
- After rebooting, Fedora 44 Workstation welcomes users with setup prompts:  
  - Connect to Wi-Fi (optional, skipped by host).  
  - Privacy settings including location services and automatic problem reporting.  
  - Time zone selection (host uses Kolkata, India).  
- **Enable third-party repositories is critical**:  
  - Required for Nvidia drivers, multimedia codecs, and other proprietary software excluded from Fedora by default due to licensing.  
- User account setup: full name, username, optional photo, password setup.  
- After configuration, system is ready for use.

[00:06:31]  
**Updating Fedora System**  
- Two main ways to update Fedora after installation:  
  1. Via **GNOME Software Center** → Updates tab → Download and install all updates, including integrated firmware.  
  2. Via terminal using the command:  
  $$ \texttt{sudo dnf upgrade} $$  
- System may have significant updates even shortly after downloading the ISO due to rolling updates and recent patches.  
- Some updates (like firmware) may require system restart to take effect.  
- After update and reboot, notifications confirm software updates installed.

[00:08:30]  
**Power Profile Configuration**  
- Fedora has three power profiles:  
  | Profile     | Description                                                   | Use Case                              | Power Consumption             | Performance                       |  
  |-------------|---------------------------------------------------------------|-------------------------------------|------------------------------|---------------------------------|  
  | Balanced    | Mix of performance and efficiency                            | Default setting                     | Moderate                     | Moderate                        |  
  | Performance | Prioritizes maximum CPU clock speed for responsiveness       | Gaming, heavy workloads             | Higher                      | High                           |  
  | Power Saver | Reduces CPU clocks for extended battery life                 | Battery-critical scenarios (e.g., cafe work) | Lowest                      | Reduced                        |  
- Default is **Balanced**. Host prefers **Performance** on an old laptop for better responsiveness. Users can switch to **Power Saver** on battery to extend life.

[00:09:57]  
**RPM Fusion: Enabling Additional Software Repositories**  
- Fedora does not ship some software by default due to licensing restrictions (e.g., proprietary codecs and drivers).  
- **RPM Fusion** provides these missing packages as pre-compiled RPMs for Fedora and its clones.  
- Two ways to enable RPM Fusion:  
  1. Graphically via Firefox web browser by downloading RPM Fusion packages from the official site.  
  2. Via terminal with a single command line that enables both free and non-free RPM Fusion repositories at once (recommended due to encountered graphical installation issues).  
- In the video, the graphical installation failed due to a mirror resolution issue ("ID is out of the bitmap range"), and the host fixed it by copying and pasting the terminal command, which included both free and non-free repos.  
- Typical command format (paraphrased):  
  $$ \texttt{sudo dnf install --nogpgcheck <RPM-Fusion-free-and-nonfree-URL>} $$  
  *(Exact line provided by the host in video description)*  
- After running the command and confirming, RPM Fusion repositories are enabled successfully.

[00:13:22]  
**Installing Multimedia Codecs via RPM Fusion**  
- Fedora includes **ffmpeg-free** by default, but it may cause version mismatches with certain software.  
- RPM Fusion provides a better supported **FFmpeg** build (non-free).  
- Recommended to swap default version with RPM Fusion’s version using:  
  $$ \texttt{sudo dnf swap ffmpeg-free ffmpeg --allow-erasing} $$  
- Command removes default free variant and installs the RPM Fusion version.  
- Allows smoother multimedia playback and compatibility.  
- Importing necessary OpenPGP keys is automated during this process.

[00:15:00]  
**Installing Common Applications: VLC and Steam**  
- **VLC media player** is recommended as the best multimedia player.  
- Installation options:  
  - Via Fedora Flatpak or Flathub (recommended because RPM package versions tend to be outdated).  
  - Flatpak apps are containerized, so they include their own dependencies, avoiding system package conflicts.  
- For gamers, installing **Steam** is straightforward:  
  $$ \texttt{sudo dnf install steam} $$  
- Steam installation will pull in all necessary dependencies from RPM Fusion non-free repository.  
- Size and dependencies details are shown during installation confirmation.  
- Once installed, Steam is ready for gaming on Fedora.

[00:18:05]  
**Installing and Using GNOME Extensions**  
- GNOME Extensions enhance and customize the GNOME desktop environment beyond default capabilities.  
- To install extensions:  
  - Visit **extensions.gnome.org** in a browser.  
  - Install the browser extension prompt to enable extension management.  
  - After installation, browse and enable desired extensions from the web interface.  
- Popular extension highlighted: **Dash to Dock**  
  - Customizes the default GNOME dock for better appearance and usability (smaller icons, adjustable padding).  
  - Supports configuration such as dock position (bottom, left, right, top), auto-hide behavior, and size limits.  
- User interface for extensions includes options to enable/disable, configure, or remove them dynamically.

[00:21:35]  
**Installing and Using GNOME Tweaks**  
- GNOME Tweaks is a powerful tool for extended system customization unavailable in the default GNOME settings.  
- Can be installed from GNOME Software by searching “Tweaks.”  
- Features include:  
  - Font customization (type, scaling factor, anti-aliasing modes).  
  - Appearance changes: cursor themes, icon themes, backgrounds, sound themes.  
  - Mouse and touchpad options (e.g., middle-click paste).  
  - Window behavior tweaks, such as enabling minimize and maximize buttons (not included in default GNOME).  
  - Adjusting window button layout for Windows-style or macOS-style.  
  - Startup application management.  
- GNOME Tweaks enhances user control over desktop look and feel, dramatically improving the Fedora GNOME experience.

[00:24:33]  
**Detailed GNOME Settings and Customizations**  
- The host reviews the GNOME Settings application, offering extensive device and system configuration:  
  - Network setup (Wi-Fi, wired, VPNs, proxies).  
  - Bluetooth scanning and device management.  
  - Display settings: resolution, refresh rate, multi-monitor behavior, and native fractional scaling (125% scaling is no longer experimental in GNOME 50).  
  - Sound control: input/output device selection, volume control, balance.  
  - Power settings revisited: button behaviors, auto-suspend timers, power-saving toggles.  
  - Multitasking: hot corner activation, dynamic/fixed number of workspaces, window snapping behaviors.  
  - Appearance: accent colors, wallpapers, light/dark mode toggle.  
  - Notifications, search preferences, online accounts integration.  
  - Sharing features for local network file and media sharing.  
  - Accessibility, privacy, security settings.  
  - System information: shows Fedora 44, GNOME 50, and that Fedora now uses **Wayland exclusively** (X11 completely removed).  
- Nvidia GPU users need to manually install proprietary drivers.

[00:28:05]  
**Conclusion**  
- The video provides a comprehensive walkthrough to successfully install Fedora Linux 44 Workstation edition from fresh download to a fully operational, customized system.  
- Key takeaways include enabling third-party repositories, performing system updates, configuring power profiles, installing multimedia codecs from RPM Fusion, installing common apps (VLC, Steam), customizing GNOME with extensions and tweaks, and using the Settings app for fine-grained control.  
- Fedora 44 is positioned as a polished, user-friendly Linux desktop environment with robust software support and modern GNOME features.

**Summary Table: Key Commands and Actions**

| Task                          | Command / Procedure                                                                                  | Notes                              |
|-------------------------------|----------------------------------------------------------------------------------------------------|----------------------------------|
| Update system via terminal     | $$ \texttt{sudo dnf upgrade} $$                                                                    | Prompts for password, updates OS |
| Enable RPM Fusion repos        | Copy-paste meta-package command from official RPM Fusion site                                      | Enables free + non-free repos     |
| Swap default FFmpeg codec      | $$ \texttt{sudo dnf swap ffmpeg-free ffmpeg --allow-erasing} $$                                   | Installs better multimedia codec |
| Install Steam                  | $$ \texttt{sudo dnf install steam} $$                                                             | Installs Steam with dependencies  |
| Install GNOME Tweaks           | Search "Tweaks" in GNOME Software center and install                                               | For extended customization       |
| Install GNOME Extensions       | Visit extensions.gnome.org → install browser extension → enable desired extensions                 | Customizes GNOME desktop          |

**Key Insights:**

- **Enabling third-party repositories (RPM Fusion) is essential for proprietary software like Nvidia drivers and codecs.**  
- **GNOME 50 on Fedora 44 fully supports Wayland, removing X11 legacy session.**  
- **Flatpak installation of apps like VLC is preferable for up-to-date and dependency-isolated packages.**  
- **GNOME Tweaks unlocks critical UI improvements missing in default GNOME, such as window buttons and font control.**  
- **Power profile management tailors performance vs. battery life for various user scenarios.**

This summary reflects the detailed and practical Fedora 44 setup and optimization workflow demonstrated in the source video transcript.
