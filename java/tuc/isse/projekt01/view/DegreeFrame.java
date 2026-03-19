/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01.view;

import java.awt.BorderLayout;
import java.awt.GridLayout;

import java.awt.Dimension;
import java.awt.event.ActionListener;
import javax.swing.JFrame;
import javax.swing.JPanel;

import tuc.isse.projekt01.model.*;

/**
 * Projekt 04, Task a: MVC Pattern - View Package
 * Projekt 04, Task d: DegreeFrame - Graphical User Interface
 * 
 * This class is part of the VIEW layer in the Model-View-Controller pattern.
 * The view package contains all GUI components:
 * - DegreeFrame: Main game window with board display
 * - BallButton: Custom button for displaying balls on the board
 * - DirectionButton: Custom button for direction selection
 * 
 * The view observes the model and updates automatically when the game state changes.
 * 
 * This class represents the main GUI window for the 90 Grad game. It implements
 * BoardObserver to automatically update the display when the board state changes.
 * 
 * Key features:
 * - 7x7 grid of BallButton elements representing the game board
 * - Direction buttons (UP, DOWN, LEFT, RIGHT) for selecting move direction
 * - Visual feedback for selected balls and directions (blue border)
 * - Automatic update when board changes via the Observer pattern
 * - Winner popup dialog when game ends
 * 
 * Methods for ActionListener management:
 * - addButtonListener() / removeButtonListener(): Manage listeners for board buttons
 * - addDirectionListener() / removeDirectionListener(): Manage listeners for direction buttons
 * 
 * The update() method refreshes the GUI to reflect current ball positions and displays
 * a winner message when the game concludes.
 */
// the GUI of the game
// observes the board and updates automatically
public class DegreeFrame extends JFrame implements BoardObserver {

    private final Board board;
    private BallButton[][] fieldButtons;
    private DirectionButton[] directionButtons;
    
    private static final int SIZE = 7;

    private BallButton selectedButton = null;
    private DirectionButton selectedDirection = null;


    public DegreeFrame(Board board) {
    	// Constructor
        super("90 Grad");
        this.board = board;

        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLayout(new BorderLayout());
        
        // BOARD PANEL
        JPanel boardPanel = new JPanel(new GridLayout(SIZE, SIZE));
        boardPanel.setPreferredSize(new Dimension(600, 600)); 
        
        fieldButtons = new BallButton[SIZE][SIZE];

        for (int row = 0; row < SIZE; row++) {
            for (int col = 0; col < SIZE; col++) {

                BallButton button = new BallButton();
                
                // store position
                button.putClientProperty("row", row);
                button.putClientProperty("col", col);

                // Selection logic
                button.addActionListener(e -> {
                    if (selectedButton != null) {
                        selectedButton.setSelected(false);
                    }

                    selectedButton = button;
                    button.setSelected(true);
                });

                fieldButtons[row][col] = button;
                boardPanel.add(button);
            }
        }
        
        add(boardPanel, BorderLayout.CENTER);
        
        // DIRECTION PANEL
        JPanel directionPanel = new JPanel(new GridLayout(4, 1, 5, 5));
        directionPanel.setPreferredSize(new Dimension(120, 600));

        directionButtons = new DirectionButton[] {
                new DirectionButton(Direction.UP),
                new DirectionButton(Direction.DOWN),
                new DirectionButton(Direction.LEFT),
                new DirectionButton(Direction.RIGHT)
        };

        for (DirectionButton button : directionButtons) {

            button.addActionListener(e -> {
                if (selectedDirection != null) {
                    selectedDirection.setSelected(false);
                }
                selectedDirection = button;
                button.setSelected(true);
            });

            directionPanel.add(button);
        }

        add(directionPanel, BorderLayout.EAST); // Direction Panel is at the right side of the Board Panel
        
        pack(); // auto size
        setLocationRelativeTo(null); // center on screen
        setVisible(true);
    }
    
    /**
     * Observer update method
     * @param board The observable board that changed
     */
    @Override
    public void update(ObservableBoard board) {

        for (int row = 0; row < SIZE; row++) {
            for (int col = 0; col < SIZE; col++) {
            	fieldButtons[row][col].setBall(board.getBall(col, row));
            }
        }
        // Show winner popup
        if (board.getWinner() != Winner.NONE) {

            javax.swing.JOptionPane.showMessageDialog(
                    this,
                    "Congratulations! " + board.getWinner() + " wins!",
                    "Game Over",
                    javax.swing.JOptionPane.INFORMATION_MESSAGE
            );
        }

    }
    
    /**
     * Adds listener from all board buttons
     * @param listener The action listener to register
     */
    public void addButtonListener(ActionListener listener) {
        for (int row = 0; row < SIZE; row++) {
            for (int col = 0; col < SIZE; col++) {
                fieldButtons[row][col].addActionListener(listener);
            }
        }
    }
    /**
     * Removes listener from all board buttons
     * @param listener The action listener to unregister
     */
    public void removeButtonListener(ActionListener listener) {
        for (int row = 0; row < SIZE; row++) {
            for (int col = 0; col < SIZE; col++) {
                fieldButtons[row][col].removeActionListener(listener);
            }
        }
    }

    /**
     * Adds listener to all direction buttons
     * @param listener The action listener to register
     */
    public void addDirectionListener(ActionListener listener) {
        for (DirectionButton button : directionButtons) {
            button.addActionListener(listener);
        }
    }

    /**
     * Removes listener from all direction buttons
     * @param listener The action listener to unregister
     */
    public void removeDirectionListener(ActionListener listener) {
        for (DirectionButton button : directionButtons) {
            button.removeActionListener(listener);
        }
    }
    // Once selected, get blue border
     /**
     * Get the currently selected ball button
     * @return The selected BallButton, or null if none selected
     */
    public BallButton getSelectedButton() {
        return selectedButton;
    }
    
    /**
     * Get the currently selected direction button
     * @return The selected DirectionButton, or null if none selected
     */
    public DirectionButton getSelectedDirection() {
        return selectedDirection;
    }


}

