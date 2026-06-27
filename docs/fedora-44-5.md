[00:00:02] This video provides a comprehensive guide on **customizing the GNOME desktop environment** across various distributions such as Ubuntu, Fedora, and Manjaro, demonstrated using GNOME 49. The tutorial covers multiple customization aspects, from installing essential software to changing themes, icons, fonts, and cursor styles. The presenter suggests starting with essential software installations to facilitate further customizations and advises backing up data before proceeding.

[00:00:35] The first essential software is **GNOME Tweaks**, which allows theme and appearance modifications. Care is needed to select the correct “GNOME Tweaks” app instead of similarly named apps for other desktop environments. Installation can be done either via the software manager or terminal. The second tool is **Extension Manager**, which simplifies the management of GNOME extensions. If unavailable via the software center, it can be installed through **FlatHub** by following tailored commands based on the user’s distribution, followed by a system reboot.

[00:01:38] After enabling FlatHub, the user installs Extension Manager by copying commands from the website for reliable installation. Using this tool, the crucial **User Themes extension** is installed, which enables full GNOME shell theme customization. Confirmation of the developer’s identity is recommended before installation.

[00:02:40] With the tools ready, the video covers installing a GNOME shell and application theme from the popular community site **gnome-look.org**. The focus is on **GTK3/4 themes** that alter the shell and applications’ appearance. The example theme, **Reversal GTK**, changes the quick settings UI to a squarish look. Users must verify the theme’s compatibility with their GNOME version.

[00:03:41] The installation involves downloading the theme archive, extracting it, and placing the main theme folder into a hidden **.themes** folder in the user’s home directory (create the folder if it does not exist). Pressing Ctrl+H enables viewing hidden folders. Verifying the theme folder’s contents ensure they include a `gnomeshell` folder or `index.theme` file to confirm correctness.

| Step                      | Description                                         |
|---------------------------|-----------------------------------------------------|
| 1. Download Theme         | From gnome-look.org, selected GTK3/4 category       |
| 2. Extract Files          | Extract archive using the file manager              |
| 3. Create .themes folder  | In home directory if it does not exist              |
| 4. Paste theme folder     | Into the newly created or existing `.themes` folder |

[00:04:39] To apply the new shell theme, use the **User Themes extension’s settings**. Note that this changes only shell UI elements (dock, panel, calendar, toggles). To style legacy applications, open GNOME Tweaks and select the installed theme under legacy application styles. However, this method does not affect modern GNOME apps like Settings or Files, which use the newer libadwaita system.

[00:05:32] The presenter demonstrates the difference: legacy applications like Terminal apply the theme styles, whereas modern apps remain with the default look. The legacy styling no longer affects modern apps as it did in earlier GNOME versions. 

[00:06:02] For **full system theming**, including modern apps, the video recommends themes with custom installation scripts from GitHub, such as the **Orchis theme**. Installation involves downloading the theme (via `zip` or `git clone`), extracting it, and running an installation shell script (`install.sh`) within the theme folder.

[00:06:40] The video emphasizes advanced theme customizations by adding flags to the install script:

- **Accent color selection:** using `-t COLOR` (e.g., `-t green`)  
- **Transparency effect control:** `--tweaks solid` for a solid (non-transparent) theme  
- **Windows button style:** `--tweaks macOS` for Mac-like buttons or default for Windows-like  
- **Apply theme to modern apps:** use `-l` flag (mandatory for GNOME 42+)  
- **Theme variant:** `-c dark` for dark mode, or default light mode  

These options are customizable in the install command before execution.

[00:08:09] After running the customized installation command, the Orchis theme can be applied via GNOME Tweaks in the Appearance tab, where both Shell and legacy application styles are set. Orchis offers multiple variants (compact, dark, light), and the example applies the **Orchis-Green-Light** theme, showing subtle transparency and rounded corners changes.

[00:08:41] The theme’s effectiveness is confirmed by opening a modern app (File Explorer), which displays full styling including Mac-style buttons and a styled sidebar. A session logout and login are required for all changes to take full effect. It’s recommended to also change the system’s **accent color** in system settings to match the theme for a cohesive look.

[00:09:16] The video briefly introduces another GitHub theme by the same developer, **Mac Tahoe**, with a similar installation process and use of the `-l` flag for modern apps. Users are encouraged to download, extract, run the install script, and apply it via Tweaks. Matching wallpaper is advised to complete visual harmony.

[00:10:14] The presenter chooses to revert to Orchis, showing the process of reapplying the install script with different flag options to customize the button style or features before final logout to refresh the desktop UI.

[00:10:38] Next, the video tackles improving the **app grid background**, suggesting the install of the **Blur My Shell** extension from Extension Manager. This adds a blurred wallpaper effect behind the panel and app menu, replacing the default solid gray background.

[00:11:06] The presenter customizes the blur:

- Disables panel blur (to avoid interfering with Orchis panel styling)
- Adjusts blur radius and brightness under "Other" tab for a balanced frosted-glass effect that maintains legibility

[00:11:38] The video then moves to installing new **icon themes** from gnome-look.org, recommending filtering by ratings to select high-quality sets. Examples used are **Tela** and **Hatter** icon packs. Downloading the correct GNOME-specific version of the icon set is critical (especially for Hatter, which has KDE vs GNOME variants).

[00:12:48] Icon installation steps:

- Extract downloaded icon archives
- Verify extracted folders contain an `index.theme` file
- Place chosen icon folders into the home directory’s hidden `.icons` folder (create if necessary)

| Step                         | Description                                            |
|------------------------------|--------------------------------------------------------|
| 1. Download icon theme       | From gnome-look.org in “Full Icon Themes” section       |
| 2. Extract archives          | Extract files and identify correct subfolders           |
| 3. Create `.icons` folder    | Hidden folder in home directory if missing               |
| 4. Copy icon folders         | Into `.icons` folder ensuring each has `index.theme`    |

[00:13:45] To activate icons, close and reopen GNOME Tweaks (to refresh icon listings), then select the desired icon variant under the Appearance tab. The video shows immediate effect on folders and other icons, highlighting how color-coordinated icons (like Hatter Green) enhance theme consistency.

[00:14:41] For dock customization, the **Dash to Dock** extension is installed and configured via Extension Manager settings. Features include:

- Dock positioning (left, right, top, bottom)  
- Icon size adjustment  
- Opacity control (including integration with Blur My Shell for blur backgrounds)  

[00:15:39] For a compact alternative, the **Dash in Panel** extension moves the dock inside the top panel and repositions calendar icons, with options for centering and resizing icons. To relocate the entire panel to the bottom, the **Just Perfection** extension is used, offering granular control over panel position and visibility of interface elements.

[00:16:39] Using Just Perfection to move the panel to the bottom gives a traditional desktop feel common in other operating systems. Users are encouraged to experiment with these layout and style options depending on preference.

[00:17:11] The video then discusses font customization. The default system font may not be ideal, so the presenter downloads the **Inter** font from Google Fonts. Installation involves:

- Extracting the font files  
- Double-clicking individual font files to install or manually copying to a `.fonts` folder in the home directory if no font viewer is available  
- Reloading GNOME Tweaks to select the new font for interface text and document text  
- Adjusting font size within Tweaks for readability — preferred over changing screen scaling for a balanced UI look  

[00:18:40] Note: The monospace font for terminals and code editors should remain a fixed-width font (often with “mono” in the name). Changing this arbitrarily causes display issues.

[00:19:06] Practical advice includes logging out and back in to see font changes applied properly.

[00:19:06] The video continues with animation enhancements for a livelier interface via extensions:

- **Dash2Dock animated:** Adds icon zoom and bounce effects with settings for autohide, opacity, rounded corners, background color, and label visibility (hiding labels reduces flicker)  
- **Desktop Cube:** Offers a 3D cube effect when switching between virtual desktops  
- **Compiz-alike Magic Lamp:** Classic minimize/maximize animation with alignment quirks (optional)  
- **Compiz Windows Effect:** Adds bouncing/wavy animations when moving/resizing windows to create a dynamic feel  

Extensions provide customizable speed and style settings.

[00:22:30] For cursor customization, gnome-look.org’s cursor section offers over a thousand cursor themes. The example used is **Bibata Modern Ice**:

- Download Linux-specific cursor version  
- Extract and move the cursor folder to the `.icons` folder in the home directory (same as icon themes)  
- Apply new cursor in GNOME Tweaks under the appearance tab  

Alternative cursor themes can be selected to match color scheme.

[00:23:31] Cursor size adjustments can be made via **System Settings → Accessibility → Seeing**, where users can increase or decrease the cursor size for comfort.

[00:23:31] Final notes include how to **undo all changes**:

- Disable or remove installed extensions via Extension Manager  
- Revert themes and fonts to default in GNOME Tweaks  
- For themes installed via `install.sh` scripts, run the removal command:

$$
./install.sh -r
$$

inside the theme directory, then log out and back in to restore the original look.

[00:24:18] The video concludes with a thank you note and encouragement for happy theming in GNOME.

---

### Key Insights and Recommendations

- **Essential tools for GNOME customization:** GNOME Tweaks, Extension Manager, User Themes extension  
- **Theme installation:** Separate shell themes and legacy application themes exist; modern GNOME apps require special handling / scripts  
- **GitHub themes like Orchis provide advanced options** for accent, transparency, button style, and theming modern apps using flags like $-l$ and $-c$  
- **Icon and cursor themes require placing proper folders inside ~/.icons** (hidden directory in home)  
- **Dock and panel appearance are highly flexible** with Dash to Dock, Dash in Panel, and Just Perfection extensions  
- **Fonts improve interface readability; prefer “Inter” font and adjust size via Tweaks rather than display scaling**  
- **Animations create a lively desktop experience but may require fine-tuning for smoothness**  
- **Backup and easy rollback strategies are essential for confident customization**  

This systematic customization approach enables a user-friendly, visually consistent GNOME desktop tailored to personal aesthetics without compromising system stability.
