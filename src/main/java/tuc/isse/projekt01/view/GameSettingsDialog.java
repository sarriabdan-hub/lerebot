/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * 
 * Projekt 06 (Bonus), Task b: Game Settings Dialog
 * 
 * This class provides a GUI dialog for configuring game settings before
 * starting a new game. It allows players to choose whether each color
 * (White and Black) should be controlled by a human or computer player.
 * 
 * TASK IMPLEMENTATION: Project 6, Task b (20 Bonus Points)
 * - User interface for selecting player types
 * - Supports all combinations:
 *   * Human vs Human
 *   * Human vs Computer
 *   * Computer vs Human
 *   * Computer vs Computer
 * 
 * PURPOSE:
 * Provides a user-friendly way to configure game modes without recompiling
 * code. This is essential for a complete game application where users want
 * flexibility in how they play.
 * 
 * USAGE:
 *   GameSettingsDialog dialog = new GameSettingsDialog(parentFrame);
 *   dialog.setVisible(true);
 *   if (dialog.isConfirmed()) {
 *       boolean whiteIsComputer = dialog.isWhiteComputer();
 *       boolean blackIsComputer = dialog.isBlackComputer();
 *       // Create appropriate players based on settings
 *   }
 */
package tuc.isse.projekt01.view;

import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;

/**
 * Dialog window for configuring game settings.
 * 
 * This class creates a modal dialog that blocks until the user
 * confirms or cancels. It uses radio buttons to let users select
 * player types for each color.
 * 
 * @author Haris Masood, Xiajiong Xu
 * @version 1.0
 */
public class GameSettingsDialog extends JDialog {

    /**
     * Radio button for selecting human player for White.
     * 
     * WHY RADIO BUTTON:
     * Radio buttons are standard UI for "choose one of two options".
     * They clearly show both options and which is selected.
     */
    private JRadioButton whiteHumanRadio;
    
    /**
     * Radio button for selecting computer player for White.
     * 
     * WHY SEPARATE FROM HUMAN:
     * Radio buttons in a ButtonGroup ensure only one can be
     * selected at a time (mutually exclusive).
     */
    private JRadioButton whiteComputerRadio;
    
    /**
     * Radio button for selecting human player for Black.
     */
    private JRadioButton blackHumanRadio;
    
    /**
     * Radio button for selecting computer player for Black.
     */
    private JRadioButton blackComputerRadio;
    
    /**
     * Button to confirm settings and close dialog.
     * 
     * WHY NEEDED:
     * Standard dialog pattern - user confirms choices or cancels.
     */
    private JButton okButton;
    
    /**
     * Button to cancel and close dialog without saving settings.
     * 
     * WHY NEEDED:
     * Allows user to change their mind and exit without applying settings.
     */
    private JButton cancelButton;
    
    /**
     * Tracks whether user clicked OK or Cancel.
     * 
     * WHY BOOLEAN:
     * Simple flag to tell caller if settings should be applied.
     * True = OK clicked, False = Cancel or window closed.
     */
    private boolean confirmed = false;

    /**
     * Constructor for GameSettingsDialog.
     * 
     * TASK: Project 6, Task b - Settings Dialog Creation
     * 
     * Creates and initializes the settings dialog with all UI components.
     * Sets up layout, adds components, and configures event listeners.
     * 
     * @param parent The parent frame (usually the main game window).
     *               Used for centering the dialog and modal behavior.
     * 
     * WHY PARENT PARAMETER:
     * - Centers dialog over main window (better UX)
     * - Makes dialog modal (blocks parent until closed)
     * - Maintains proper window hierarchy
     * 
     * MODAL BEHAVIOR:
     * The dialog blocks the parent window until it's closed. This
     * prevents users from interacting with the game while configuring
     * settings, avoiding confusion.
     */
    public GameSettingsDialog(Frame parent) {
        // Call JDialog constructor with parent and modality
        // "Game Settings" = window title
        // true = modal (blocks parent window)
        super(parent, "Game Settings", true);
        
        // Initialize and layout all components
        initializeComponents();
        
        // Size the dialog appropriately
        // WHY pack(): Automatically sizes to fit all components nicely
        pack();
        
        // Center dialog on screen (or over parent)
        // WHY: Better UX than appearing in corner
        setLocationRelativeTo(parent);
        
        // Set what happens when user closes window with X button
        // DISPOSE_ON_CLOSE: Closes dialog, returns control to parent
        setDefaultCloseOperation(DISPOSE_ON_CLOSE);
    }

    /**
     * Initializes all UI components and sets up the layout.
     * 
     * WHY SEPARATE METHOD:
     * Constructor is cleaner when complex initialization is extracted.
     * Also makes code more maintainable - all UI setup in one place.
     * 
     * LAYOUT STRUCTURE:
     * - Main panel with BorderLayout
     * - Settings panel in center (GridLayout for player choices)
     * - Button panel at bottom (OK/Cancel buttons)
     * 
     * WHY THIS LAYOUT:
     * - BorderLayout: Standard dialog pattern (content + buttons)
     * - GridLayout: Neat alignment of radio button groups
     * - Looks professional and is easy to understand
     */
    private void initializeComponents() {
        // Main container panel
        JPanel mainPanel = new JPanel(new BorderLayout(10, 10));
        mainPanel.setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10));
        
        // === Settings Panel (Center) ===
        // WHY GridLayout(2, 1): Two rows (White, Black), one column
        JPanel settingsPanel = new JPanel(new GridLayout(2, 1, 10, 10));
        
        // --- White Player Settings ---
        JPanel whitePanel = createPlayerPanel(
            "White Player:", 
            "Human", 
            "Computer"
        );
        
        // Initialize White player radio buttons
        whiteHumanRadio = findRadioButton(whitePanel, "Human");
        whiteComputerRadio = findRadioButton(whitePanel, "Computer");
        whiteHumanRadio.setSelected(true); // Default: Human
        
        settingsPanel.add(whitePanel);
        
        // --- Black Player Settings ---
        JPanel blackPanel = createPlayerPanel(
            "Black Player:", 
            "Human", 
            "Computer"
        );
        
        // Initialize Black player radio buttons
        blackHumanRadio = findRadioButton(blackPanel, "Human");
        blackComputerRadio = findRadioButton(blackPanel, "Computer");
        blackHumanRadio.setSelected(true); // Default: Human
        
        settingsPanel.add(blackPanel);
        
        mainPanel.add(settingsPanel, BorderLayout.CENTER);
        
        // === Button Panel (Bottom) ===
        JPanel buttonPanel = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        
        // OK Button
        okButton = new JButton("OK");
        okButton.addActionListener(new ActionListener() {
            /**
             * Handles OK button click.
             * 
             * WHY THIS CODE:
             * When user clicks OK, we:
             * 1. Set confirmed flag to true (settings accepted)
             * 2. Close dialog
             * Caller can then check isConfirmed() and read settings.
             */
            @Override
            public void actionPerformed(ActionEvent e) {
                confirmed = true;
                dispose(); // Close dialog
            }
        });
        buttonPanel.add(okButton);
        
        // Cancel Button
        cancelButton = new JButton("Cancel");
        cancelButton.addActionListener(new ActionListener() {
            /**
             * Handles Cancel button click.
             * 
             * WHY THIS CODE:
             * When user clicks Cancel, we:
             * 1. Leave confirmed as false (settings rejected)
             * 2. Close dialog
             * Caller can check isConfirmed() and ignore settings.
             */
            @Override
            public void actionPerformed(ActionEvent e) {
                confirmed = false;
                dispose(); // Close dialog
            }
        });
        buttonPanel.add(cancelButton);
        
        mainPanel.add(buttonPanel, BorderLayout.SOUTH);
        
        // Add main panel to dialog
        add(mainPanel);
    }

    /**
     * Creates a panel for selecting player type (Human or Computer).
     * 
     * WHY THIS METHOD:
     * Both White and Black need identical UI structure. This method
     * creates that structure once and reuses it, following DRY principle.
     * 
     * @param labelText Text to display (e.g., "White Player:")
     * @param option1Text Text for first radio button (e.g., "Human")
     * @param option2Text Text for second radio button (e.g., "Computer")
     * @return JPanel containing label and radio buttons
     * 
     * WHY THESE PARAMETERS:
     * Makes method flexible - can create panels for any color with
     * any option names, making it reusable and maintainable.
     */
    private JPanel createPlayerPanel(String labelText, 
                                    String option1Text, 
                                    String option2Text) {
        // Panel with label on left, radio buttons on right
        JPanel panel = new JPanel(new BorderLayout(5, 5));
        panel.setBorder(BorderFactory.createEtchedBorder());
        
        // Label (e.g., "White Player:")
        JLabel label = new JLabel(labelText);
        label.setFont(new Font("Arial", Font.BOLD, 14));
        panel.add(label, BorderLayout.WEST);
        
        // Radio buttons panel
        JPanel radioPanel = new JPanel(new FlowLayout(FlowLayout.LEFT));
        
        // Create radio buttons
        JRadioButton option1 = new JRadioButton(option1Text);
        JRadioButton option2 = new JRadioButton(option2Text);
        
        // ButtonGroup ensures only one can be selected
        // WHY: Radio buttons need ButtonGroup to enforce mutual exclusivity
        ButtonGroup group = new ButtonGroup();
        group.add(option1);
        group.add(option2);
        
        // Add to panel
        radioPanel.add(option1);
        radioPanel.add(option2);
        
        panel.add(radioPanel, BorderLayout.CENTER);
        
        return panel;
    }

    /**
     * Finds a radio button by its text within a panel.
     * 
     * WHY THIS METHOD:
     * Helper to retrieve radio buttons created in createPlayerPanel().
     * Searches panel's components to find the radio button with
     * matching text.
     * 
     * @param panel The panel to search
     * @param text The button text to find
     * @return The JRadioButton with matching text, or null if not found
     * 
     * WHY THIS APPROACH:
     * createPlayerPanel() creates components internally, so we need
     * a way to retrieve them after creation. This searches by text
     * rather than maintaining separate variables.
     */
    private JRadioButton findRadioButton(JPanel panel, String text) {
        // Search all components in the panel
        for (Component comp : panel.getComponents()) {
            // Check if component is a panel (nested structure)
            if (comp instanceof JPanel) {
                JPanel subPanel = (JPanel) comp;
                // Recursively search nested panel
                for (Component subComp : subPanel.getComponents()) {
                    if (subComp instanceof JRadioButton) {
                        JRadioButton radio = (JRadioButton) subComp;
                        if (radio.getText().equals(text)) {
                            return radio;
                        }
                    }
                }
            }
        }
        return null;
    }

    // =========================================================================
    // PUBLIC METHODS - Settings Retrieval
    // =========================================================================

    /**
     * Checks if user confirmed the settings (clicked OK).
     * 
     * USAGE:
     *   if (dialog.isConfirmed()) {
     *       // Use the selected settings
     *   }
     * 
     * @return true if OK was clicked, false if Cancel or window closed
     * 
     * WHY THIS METHOD:
     * Caller needs to know if settings should be applied. This distinguishes
     * between "user clicked OK" vs "user cancelled or closed window".
     */
    public boolean isConfirmed() {
        return confirmed;
    }

    /**
     * Checks if White player is set to Computer.
     * 
     * TASK: Project 6, Task b - Read player type selection
     * 
     * Returns the user's choice for White player type. This value
     * should only be read if isConfirmed() returns true.
     * 
     * @return true if Computer is selected, false if Human is selected
     * 
     * WHY BOOLEAN RETURN:
     * Simple and clear: true = computer, false = human. Caller can
     * easily use this in if statements or ternary operators.
     * 
     * USAGE:
     *   Player whitePlayer = dialog.isWhiteComputer() ?
     *       new ComputerPlayer(Color.WHITE, board) :
     *       new FramePlayer(Color.WHITE, board, frame);
     */
    public boolean isWhiteComputer() {
        return whiteComputerRadio.isSelected();
    }

    /**
     * Checks if Black player is set to Computer.
     * 
     * TASK: Project 6, Task b - Read player type selection
     * 
     * Returns the user's choice for Black player type. This value
     * should only be read if isConfirmed() returns true.
     * 
     * @return true if Computer is selected, false if Human is selected
     * 
     * WHY BOOLEAN RETURN:
     * Same rationale as isWhiteComputer() - simple, clear, easy to use.
     * 
     * USAGE:
     *   Player blackPlayer = dialog.isBlackComputer() ?
     *       new ComputerPlayer(Color.BLACK, board) :
     *       new FramePlayer(Color.BLACK, board, frame);
     */
    public boolean isBlackComputer() {
        return blackComputerRadio.isSelected();
    }

    /**
     * Displays the dialog and waits for user response.
     * 
     * WHY OVERRIDE:
     * Provides semantic clarity - calling show() makes it obvious
     * that this is a dialog that will block until user responds.
     * 
     * NOTE: This calls setVisible(true) which blocks until dialog closes
     * (because dialog is modal).
     */
    public void show() {
        setVisible(true);
    }
}
