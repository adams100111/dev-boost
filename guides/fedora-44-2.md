Live referance: https://kskroyal.com/things-to-do-after-installing-fedora-44
[00:00:00]  
**Introduction and Overview**  
This video outlines **10 essential tasks to perform immediately after installing Fedora 44**. These steps aim to customize the user interface, install critical applications and fonts, optimize system performance, and enhance the overall desktop experience. The recommendations largely apply to future Fedora versions as well.

---

[00:00:54]  
**System Update and Repository Configuration**  
- The first critical step is to **update the Fedora system**.  
- Prior to updating, optimize the **DNF package manager** configuration by adding specific lines to speed up package downloads via the terminal.  
- Execute the system update command and then **restart the computer** to apply updates.  
- Enable **third-party repositories** for accessing additional software:  
  - This can be done through the Software Center’s pop-up prompt or manually by navigating to Software Repositories.  
  - Enable **RPM Fusion repositories** using command-line instructions, which provide access to multimedia and third-party packages unavailable in Fedora's default repos.  
- Install multimedia codecs required for smooth video playback via terminal commands.  

---

[00:01:51]  
**GPU Driver Installation**  
- For better performance in graphics-intensive applications, **install proprietary GPU drivers** for Nvidia or AMD hardware.  
- Fedora RPM Fusion offers a command to automatically detect and install the appropriate driver.  
- Additionally, install CUDA support packages for Nvidia GPUs if required.  
- After installation, reboot the system to activate drivers.  
- For hardware-accelerated browser video playback, visit the vendor’s official GPU driver page and install the recommended driver.  
- The video demonstrates installing Nvidia’s proprietary drivers specifically.  

---

[00:04:02]  
**Terminal Customization with Starship**  
- Fedora ships with the default **X terminal and bash shell**. To improve the visual appeal and functionality:  
  - Install **Starship**, a modern shell prompt.  
  - Download and install a **Nerd Font**, preferably **Fira Code** (bold variant recommended).  
  - Change the terminal font to Fira Code.  
  - Enable Starship by appending a configuration line to the bash configuration file (`.bashrc`).  
  - Reload the terminal configuration or restart the terminal to see the new prompt.  
  - Customize Starship further via themes by referring to Starship presets and running related commands.  
- Result: a cleaner, more modern, and polished command-line interface.  

---

[00:06:19]  
**Installing Essential Packages, Applications, and Fonts**  
- Run terminal commands to install **useful tools and development packages** that enhance functionality.  
- Install GUI applications through the Fedora app store or commands, including:  
  - **OBS Studio** (screen recording/streaming)  
  - **VS Code** (code editor)  
  - **GParted** (disk partitioning)  
  - **VLC** (media player)  
  - **Fresh** (text editor)  
- Install **important open-source fonts** using a respective command for better text rendering.  
- Install and configure: 
  - **GNOME Tweaks**  
  - **Extension Manager**  
- These tools allow interface customization (e.g., window buttons positioning, new window centering).  

---

[00:07:35]  
**GNOME Desktop Environment Customization**  
- Using GNOME Tweaks:  
  - Adjust UI elements such as maximize/minimize buttons and new window positioning.  
- Using Extension Manager:  
  - Install various GNOME extensions to improve the desktop’s look and functionality.  
  - The video recommends several extensions aimed at modernizing the desktop environment.  

---

[00:09:06]  
**Visual Enhancements and Input Device Settings**  
- Install and configure the **Blur My Shell extension** to add system-wide blur effects, improving visual polish and appeal.  
- For laptops:  
  - Adjust mouse and touchpad settings including pointer speed, tap-to-click, and scrolling method/direction.  
- Under Appearance settings:  
  - Switch between **Light and Dark modes**.  
  - Select preferred accent colors to customize the desktop theme.  

---

[00:10:11]  
**Accessibility and Display Settings**  
- For improved readability:  
  - Enable **Large Text** in accessibility settings if on a high-resolution or small display.  
  - Increase cursor size from the same menu if needed.  
  - In Display Settings, set scaling to **125%** to make UI elements larger and clearer.  

---

[00:11:03]  
**KDE Connect Installation for Mobile Integration**  
- Install **KDE Connect** on Fedora and your Android/iPhone for seamless wireless integration over Wi-Fi.  
- Features include:  
  - Wireless file sharing  
  - Clipboard synchronization  
  - Remote control functions  
- The two devices are paired by running the app on both ends and connecting via the same network.  

---

[00:12:02]  
**Backup Solutions: Pika Backup and Time Shift**  
- Fedora offers various backup tools; recommended are:  
  - **Pika Backup**: user-friendly tool that allows creating local or remote backups with encryption. Focused on personal files, *does not support full system recovery*.  
  - **Time Shift**: command-line tool to create system snapshots of root and home directories, enabling full system state recovery without reinstalling Fedora.  
- Both tools allow backups to local drives and cloud storage solutions, enhancing data security and recovery options.  

---

[00:12:52]  
**Installing and Using AI Tools: Open Code and LM Studio**  
- Install **Open Code**, a free AI agent that automates tasks and troubleshooting via simple prompts.  
  - Example use: removing problematic packages automatically.  
  - After installation, launch and select a free AI model to get started.  
- For offline AI models, use **LM Studio**:  
  - Download and install the app image.  
  - Load models such as **Gemma 4** for local AI operations.  
  - LM Studio offers chat interfaces for question answering, image analysis, and AI-powered coding assistance integrated with VS Code.  
- The video references a separate tutorial for coding with Gemma 4 in VS Code.  

---

[00:15:13]  
**Configuring Keyboard Shortcuts and Performance Optimization**  
- Fedora allows creation of **custom keyboard shortcuts** to speed up workflows:  
  - Open Settings > Keyboard > Keyboard Shortcuts to assign actions (e.g., shortcut to open home directory instantly).  
- For laptops with powerful CPUs:  
  - Install **auto CPU frequency** tool to allow full CPU control and maximize performance.  
  - Before installing, uninstall **TLP** to prevent conflicts.  
  - Enable the auto CPU frequency daemon service and select CPU profiles:  
    | Profile        | Description                        |  
    |----------------|----------------------------------|  
    | Default        | Balanced performance              |  
    | Performance    | Maximizes CPU power output       |  
- This optimization is recommended only for systems capable of handling increased power consumption and thermal output.  

---

[00:16:26]  
**Conclusion and Video Wrap-Up**  
- These 10 tasks are presented as the **top recommended post-installation configurations for Fedora 44** to optimize and personalize the user experience.  
- The video creator invites feedback and encourages subscribing for more Fedora and Linux-related content.  

---

### Summary Table of Top 10 Post-Installation Tasks for Fedora 44  

| Step # | Task Description                          | Key Tools/Commands                              | Outcome/Benefit                              |  
|--------|-------------------------------------------|------------------------------------------------|----------------------------------------------|  
| 1      | Update system and enable repositories    | Optimize DNF config, RPM Fusion enablement    | Faster updates, access to third-party packages |  
| 2      | Install GPU drivers                       | RPM Fusion driver installer, CUDA              | Improved graphics performance                  |  
| 3      | Customize terminal with Starship         | Install Fira Code Nerd Font, Starship config   | Modern, clean shell prompt                      |  
| 4      | Install essential packages/apps/fonts    | Obs Studio, VS Code, GParted, VLC, fonts, GNOME Tweaks | Enhanced workflow and visual appeal            |  
| 5      | Customize GNOME desktop                   | GNOME Tweaks, Extension Manager                | Interface control and enhancements             |  
| 6      | Add blur effects & adjust input settings | Blur My Shell, Mouse/Touchpad settings          | Polished desktop look, improved input handling |  
| 7      | Accessibility & display scaling           | Large Text, cursor size, 125% scaling          | Better readability and UI usability            |  
| 8      | Set up mobile integration with KDE Connect | KDE Connect app (desktop and mobile)            | Seamless file sharing & device integration      |  
| 9      | Backup setup                             | Pika Backup, Time Shift                         | Easy file backup and system snapshots          |  
| 10     | AI assistance and system automation      | Open Code, LM Studio                            | Task automation, offline AI capabilities       |  
| 11*    | Custom keyboard shortcuts & CPU tuning   | Keyboard shortcut settings, auto CPU frequency  | Faster workflow, improved CPU performance      |  

*Note: The CPU tuning and keyboard shortcut setup step is included as part of the final recommendations and complements performance.  

---

**Key Insights:**  
- Proper system and repository setup ensures access to comprehensive software ecosystems.  
- Installing hardware-specific drivers profoundly affects performance, especially GPU-related tasks.  
- User interface customization (terminal, GNOME desktop) significantly improves user experience and productivity.  
- Adding blur effects and accessibility adjustments make the desktop environment visually pleasant and usable for a wider audience.  
- Integration tools like KDE Connect streamline cross-device workflows critical for mobile-laptop user synergy.  
- Automated backup and system snapshot tools are essential for data security and disaster recovery.  
- Incorporation of AI tools such as Open Code and LM Studio represents a forward-thinking approach to system management on Fedora.  
- Performance tuning through CPU management is targeted toward power users with high-demand use cases.  

---

This structured guidance provides a comprehensive, practical workflow for Fedora 44 users immediately after installation, enabling an optimized, personalized, and secure computing environment.
