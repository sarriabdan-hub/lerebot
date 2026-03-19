/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 * 
 */
package tuc.isse.projekt01.controller;

import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.NotInRangeException;
import tuc.isse.projekt01.model.NotYourBallException;
import tuc.isse.projekt01.model.OutOfGameException;
import tuc.isse.projekt01.view.BallButton;
import tuc.isse.projekt01.view.DegreeFrame;
import tuc.isse.projekt01.view.DirectionButton;

/**
 * Projekt 04, Task e: FramePlayer - GUI-based Player Implementation
 * 
 * This class extends Player and implements ActionListener to handle user interactions
 * with the DegreeFrame GUI. It manages the two-step process of making a move:
 * 1. User selects a ball by clicking on the board
 * 2. User selects a direction by clicking a direction button
 * 
 * The FramePlayer registers itself as an ActionListener when it's the active player's
 * turn (in doTurn()), and unregisters after completing a move. This ensures only the
 * active player can make moves at any given time.
 * 
 * Exception handling is implemented to catch illegal moves (NotYourBallException,
 * OutOfGameException, NotInRangeException) and display error messages to the user.
 */
public class FramePlayer extends Player implements ActionListener {
    
    private final DegreeFrame frame;
    private BallButton selectedBall;
    private DirectionButton selectedDirection;
    
    /**
     * Constructor for FramePlayer
     * 
     * @param color The color of this player (WHITE or BLACK)
     * @param board The game board
     * @param frame The GUI frame for user interaction
     */
    public FramePlayer(Color color, Board board, DegreeFrame frame) {
        super(color, board);
        this.frame = frame;
        this.selectedBall = null;
        this.selectedDirection = null;
    }
    
    /**
     * Projekt 04, Task e: doTurn() - Register as ActionListener
     * 
     * This method is called when it's this player's turn. Unlike ConsolePlayer which
     * waits for input synchronously, FramePlayer registers itself as an ActionListener
     * to handle button clicks asynchronously. The actual move happens in actionPerformed()
     * when the user completes the ball and direction selection.
     */
    @Override
    public void doTurn() {
        // Reset selections
        selectedBall = null;
        selectedDirection = null;
        
        // Register this player as listener for board and direction buttons
        frame.addButtonListener(this);
        frame.addDirectionListener(this);
    }
    
    /**
     * Projekt 04, Task e: actionPerformed() - Handle User Input
     * 
     * This method handles button clicks from the GUI. It implements a two-step process:
     * 1. When a board button is clicked, store the selected ball
     * 2. When a direction button is clicked, execute the move
     * 
     * @param e The action event containing the button that was clicked
     * 
     * After a complete move (ball + direction selected), the player unregisters itself
     * as an ActionListener to prevent further input until it's their turn again.
     * 
     * Exception handling catches illegal moves and displays error dialogs to the user.
     */
    @Override
    public void actionPerformed(ActionEvent e) {
        Object source = e.getSource();
        
        // Handle ball button click
        if (source instanceof BallButton) {
            selectedBall = (BallButton) source;
            // Ball selection is handled by the button's own listener in DegreeFrame
            return;
        }
        
        // Handle direction button click
        if (source instanceof DirectionButton) {
            selectedDirection = (DirectionButton) source;
            
            // If both ball and direction are selected, execute the move
            if (selectedBall != null && selectedDirection != null) {
                executeMoveAndCleanup();
            }
        }
    }
    
    /**
     * Helper method to execute the move and cleanup after completion
     * 
     * This method retrieves the ball position from the selected button,
     * gets the direction, attempts to move the ball, and handles any exceptions.
     * After the move (successful or not), it unregisters the listeners.
     */
    private void executeMoveAndCleanup() {
        try {
            // Get ball position from button properties
            Integer row = (Integer) selectedBall.getClientProperty("row");
            Integer col = (Integer) selectedBall.getClientProperty("col");
            Direction direction = selectedDirection.getDirection();
            
            // Validate we have the required information
            if (row == null || col == null || direction == null) {
                showError("Invalid selection. Please try again.");
                return;
            }
            
            // Execute the move
            board.moveBall(color, col, row, direction);
            
            // Move successful - unregister listeners (turn is complete)
            frame.removeButtonListener(this);
            frame.removeDirectionListener(this);
            
            // Reset selections
            selectedBall = null;
            selectedDirection = null;
            
        } catch (NotYourBallException e) {
            showError("That's not your ball! Please select a " + color + " ball.");
        } catch (OutOfGameException e) {
            showError("That ball cannot move out of the game field!");
        } catch (NotInRangeException e) {
            showError("Invalid move! The ball cannot move to that position.");
        } catch (Exception e) {
            showError("An error occurred: " + e.getMessage());
        }
    }
    
    /**
     * Helper method to display error messages to the user
     */
    private void showError(String message) {
        javax.swing.JOptionPane.showMessageDialog(
            frame,
            message,
            "Invalid Move",
            javax.swing.JOptionPane.ERROR_MESSAGE
        );
    }
}
