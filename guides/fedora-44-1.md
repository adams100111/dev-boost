[00:00:01]  
**Introduction to Fedora 44 with Snapshot and Rollback Support**  
The video begins by introducing the installation of **Fedora 44** featuring **full snapshot and rollback support** using **Snapper** and **GRUB BTRFS**. A significant highlight is Fedora's native integration of **DNF5** with **PackageKit**, meaning snapshots can now be created seamlessly beyond terminal commands—through graphical package managers such as **GNOME Software** and **KDE Discover**. This marks a major usability improvement making snapshot and rollback operations more **user-friendly, consistent, and complete**. The tutorial aims to guide the viewer through a clean installation and configuration of this new snapshot-enabled system from scratch.

[00:01:12]  
**Starting the Fedora Live Installer**  
- Boot the system using the Fedora Live installer ISO.  
- Select “start Fedora Workstation live” to enter the live environment.  
- On the Fedora welcome screen, initiate installation by clicking “install Fedora Linux.”  
- Choose language (English US in the example) and keyboard layout.  

[00:01:49]  
**Preparing for Custom Disk and Partition Setup**  
- On the installation method screen, change from “Use entire disk” to manual disk selection.  
- Select the target disk for Fedora installation.  
- Launch the **storage editor** to manually create partitions and **BTRFS subvolumes**.  
- If disk is new/unformatted, create a **GPT partition table** (recommended for modern UEFI systems).  
- Option to overwrite disk with zeros (secure wipe) is available but *not necessary* for most users. Warning to ensure no important data remains on selected disk.

[00:04:02]  
**Partition Creation**  
- Create the **EFI System Partition (ESP):**  
  - Type: EFI system partition  
  - Mount point: `/boot/efi`  
  - Size: 1 GiB (Fedora installer uses decimal GB; input approximately 1.0737 GB)  
  - Name: ESP  
- Create the **main BTRFS partition:**  
  - Type: BTRFS  
  - Size: Use remaining disk space  
  - Name: Fedora  
  - No mount point assigned here, as subvolumes will handle mounts.  
- No swap partition created, relying on Fedora’s default **ZRAM** for compressed, fast swap in memory instead of disk swap.  
- No separate `/boot` partition; instead, `/boot` remains inside the main BTRFS root subvolume to facilitate snapshot consistency across system, kernel, and initramfs.

[00:06:33]  
**Understanding BTRFS Subvolumes**  
- BTRFS subvolumes act like flexible partitions but share a single file system’s total storage dynamically, unlike fixed-size traditional partitions (e.g., EXT4).  
- Benefits include:  
  - No need to pre-allocate fixed sizes (dynamic growth/shrink)  
  - Efficient disk usage preventing unused or overflow space issues  
  - Facilitates more granular snapshotting and rollback management  

[00:07:32]  
**Creating Subvolumes and Their Purpose**  

| Subvolume Name  | Mount Point                    | Purpose/Notes                                                                                   |
|-----------------|-------------------------------|-----------------------------------------------------------------------------------------------|
| root            | `/`                           | Core OS files, binaries, system configurations; main Snapper config for system snapshots      |
| home            | `/home`                       | User data, personal files; separate Snapper config for user data snapshotting                 |
| opt             | `/opt`                        | Third-party software installations (optional but recommended for cleanliness)                 |
| cache           | `/var/cache`                  | Temporary, recreatable cache data; avoids snapshot bloat                                     |
| log             | `/var/log`                    | System logs stored separately to prevent snapshot growth; retained after rollback            |
| spool           | `/var/spool`                  | Queued data like print/mail queues; changes frequently and excluded from snapshots            |
| temp            | `/var/temp`                   | Temporary files persisting across reboots (on-disk storage, different from RAM-backed `/tmp`)  |
| containers      | `/var/lib/containers`         | Container images/data for Podman/Docker (optional based on use)                               |
| flatpak         | `/var/lib/flatpak`            | Storage for Flatpak apps and runtimes to keep snapshots smaller (frequent updates)           |
| GDM             | `/var/lib/gdm`                | Important writable directory during read-only boot from snapshots to avoid login boot issues |
| libvirt         | `/var/lib/libvirt`            | Virtual machine images and configs for KVM (optional)                                        |

- The separation isolates frequently changing or large data from `root`, improving snapshot efficiency and reliability, especially when rolling back.  
- The special case of GDM subvolume ensures that the display manager can write to necessary files during boot from a read-only snapshot.

[00:16:19]  
**Finalizing Installation and Initial System Start**  
- After creating partitions and subvolumes, the installer validates the storage layout.  
- Proceed to install Fedora 44; reboot into initial user setup when complete.  
- Fedora 44 features **GNOME 50** desktop environment.  
- Terminal inspection confirms all subvolumes are mounted according to plan.  
- A system-created `var-lib-machines` subvolume is noted (used internally by systemd for containers).

[00:18:37]  
**Adding Compression to BTRFS Mounts**  
- Default Fedora installs automatically enable BTRFS compression (`compress=zstd`), but this is missing in the custom setup’s `/etc/fstab`.  
- The guide adds `compress=zstd:1` option to all BTRFS subvolumes to improve disk space usage and performance.  
- Reboot required for changes to take effect. Post-reboot, compression is verified as active.

[00:20:29]  
**Setting Up Snapper, grub-btrfs, and BTRFS Assistant**  
- These tools provide:  
  - Automated snapshot creation before/after package manager changes  
  - Integration of snapshots into the GRUB boot menu for easy rollback  
  - Graphical interface for snapshot management  
- The video references a **GitHub repository** containing an automated installer script to set up Snapper, grub-btrfs, and BTRFS Assistant along with DNF5 integration and rollback hooks.  
- After running the installer, Snapper configs exist for both `root` and `home` subvolumes.  
- Snapper snapshot subvolumes are visible for system and home, confirming proper setup.

[00:22:16]  
**Testing Automatic Snapshots on Package Operations**  

- Installing `htop` via terminal targets DNF5 backend:  
  - Snapper automatically creates **pre and post snapshots** for the root subvolume.  
  - Diffing snapshots shows file changes associated with the package installation.  
  - Undoing the installation via Snapper’s “undo change” functionality successfully removes `htop`.  
  - Reapplying the undo with reversed snapshot numbers can restore the package.

[00:23:56]  
**Major Fedora 44 Improvement: GUI Software Snapshot Integration**  
- Previously, GUI package managers used backends different from terminal DNF, causing inconsistency in snapshot support.  
- Fedora 44 replaces the PackageKit backend with DNF5 (based on libdnf5), unifying all RPM package management across CLI and GUI tools:  
  - Terminal (DNF)  
  - GNOME Software  
  - KDE Discover  
  - Cockpit  
- This unification ensures consistent snapshot creation regardless of installation method.  

[00:24:30]  
**Testing GUI Package Installation and Snapper Integration**  
- Example: installing `gedit` via GNOME Software selecting the **Fedora RPM package** source (important because Flatpaks do not trigger Snapper snapshots).  
- Snapper successfully auto-created the pre and post snapshots for this GUI installation.  
- Undoing the installation works similarly, confirming rollback capability.  
- GNOME Software UI may not instantly reflect package removal after rollback due to cache; a logout/login cycle refreshes the UI showing accurate package status.

[00:27:32]  
**Additional Resources and Conclusion**  
- The presenter invites viewers to explore more about Snapper usage via the GitHub repository, which includes:  
  - Manual snapshot creation examples  
  - Undo change operations covering both root and home subvolumes for watertight rollback  
- Official Snapper documentation and BTRFS Assistant project page recommended for advanced learning on rollback and snapshot management.  
- The system is now fully configured for robust snapshot and rollback, leveraging Fedora 44’s new DNF5 integration and BTRFS snapshot capabilities.  

**End note:** The video closes with thanks and a farewell message.

---

### Key Takeaways
- **Fedora 44** introduces native **DNF5 integration with PackageKit**, enabling snapshots for both terminal and GUI app installs/updates.  
- Use of **BTRFS subvolumes** avoids fixed partition sizing, improving flexibility and snapshot efficiency.  
- Creating separate subvolumes for frequently changing directories prevents snapshot bloat.  
- **Snapper, grub-btrfs, and BTRFS Assistant** provide full snapshot/rollback lifecycle management including boot menu integration.  
- Compression with **`compress=zstd`** enhances performance and storage efficiency on BTRFS.  
- Rollbacks apply cleanly to both system files and personal user data (`root` and `home`).  
- GUI and CLI package management share a unified backend under Fedora 44, bringing coherence to snapshot support across tools.  
- Flatpak packages remain outside snapshot transaction flows as they use different management systems.

---

### BTRFS Subvolume Summary Table

| Subvolume      | Mount Point                | Purpose                                                    | Snapper Configured? | Optional?        |
|----------------|---------------------------|------------------------------------------------------------|--------------------|------------------|
| root           | `/`                       | Core OS files, binaries, system configurations             | Yes                | No               |
| home           | `/home`                   | User personal data                                          | Yes                | No               |
| opt            | `/opt`                    | Third-party software                                       | No                 | Yes              |
| cache          | `/var/cache`              | Temporary application cache                                 | No                 | No               |
| log            | `/var/log`                | System logs                                                | No                 | No               |
| spool          | `/var/spool`              | Queued jobs (print/mail)                                   | No                 | No               |
| temp           | `/var/temp`               | Temporary files persistent across reboots                   | No                 | No               |
| containers     | `/var/lib/containers`     | Container images and data                                  | No                 | Yes              |
| flatpak        | `/var/lib/flatpak`        | Flatpak application data                                   | No                 | Yes              |
| GDM            | `/var/lib/gdm`            | Writable display manager data on read-only boot            | No                 | No               |
| libvirt        | `/var/lib/libvirt`        | Virtual machine images for virtualization                  | No                 | Yes              |

---

This summary captures the full installation, configuration, and operational insights strictly supported by the transcript content.
