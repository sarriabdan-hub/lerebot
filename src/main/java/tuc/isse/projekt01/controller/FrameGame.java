/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 * 
 */
package tuc.isse.projekt01.controller;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.BoardObserver;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.ObservableBoard;
import tuc.isse.projekt01.model.Winner;
import tuc.isse.projekt01.view.DegreeFrame;

/**
 * Projekt 04, Task f: FrameGame - GUI-based Game Controller
 * 
 * This class extends Game and implements BoardObserver to manage the game flow
 * for the GUI version of 90 Grad. It coordinates between the players and the GUI,
 * handling turn switching and game end conditions.
 * 
 * Key responsibilities:
 * - Start the game by asking the first player to make a move (doGame)
 * - Observe board changes through the Observer pattern
 * - Switch to the next player after each move (in update method)
 * - Detect game end and disable GUI when there's a winner
 * - Display winner information to the user
 * 
 * The update() method is called automatically after each ball movement thanks to
 * the Observer pattern, allowing the game to react to board changes without polling.
 */
public class FrameGame extends Game implements BoardObserver {
    
    private final DegreeFrame frame;
    
    /**
     * Constructor for FrameGame
     * 
     * @param frame The GUI frame for the game
     * @param board The game board (must be ObservableBoard)
     * @param whitePlayer The white player
     * @param blackPlayer The black player
     */
    public FrameGame(DegreeFrame frame, Board board, Player whitePlayer, Player blackPlayer) {
        super(board);
        this.frame = frame;
        
        // Set the players
        this.player1 = whitePlayer;
        this.player2 = blackPlayer;
        
        // White player starts
        this.currentPlayer = (whitePlayer.getColor() == Color.WHITE) ? whitePlayer : blackPlayer;
        
        // Register this game controller as observer to receive board updates
        if (board instanceof ObservableBoard) {
            ((ObservableBoard) board).addObserver(this);
        }
    }
    
    /**
     * Projekt 04, Task f: doGame() - Start the Game
     * 
     * This method initiates the game by asking the active player (whitePlayer by default)
     * to make their first move. Unlike ConsoleGame which runs in a loop, FrameGame
     * only starts the first turn here. Subsequent turns are triggered automatically
     * in the update() method after each move is completed.
     * 
     * The game flow continues through the Observer pattern: move -> update() -> next move.
     */
    @Override
    public void doGame() {
        // Ask the current player to take their turn
        // This registers them as ActionListener in the GUI
        currentPlayer.doTurn();
    }
    
    /**
     * Projekt 04, Task f: update() - Handle Board Changes
     * 
     * This method is called automatically by ObservableBoard after each ball movement.
     * It checks if the game has ended (winner found) or continues by switching players.
     * 
     * Game flow:
     * 1. Player clicks ball and direction -> move executed
     * 2. ObservableBoard notifies observers (calls this update method)
     * 3. If no winner: switch players and ask next player for their turn
     * 4. If winner found: disable all buttons and display winner message
     * 
     * @param board The observable board that changed
     */
    @Override
    public void update(ObservableBoard board) {
        Winner winner = board.getWinner();
        
        // Check if game has ended
        if (winner != Winner.NONE) {
            // Game over - disable all buttons to prevent further moves
            disableAllButtons();
            
            // Display winner message
            String winnerMessage = "Game Over! " + winner + " wins!";
            javax.swing.JOptionPane.showMessageDialog(
                frame,
                winnerMessage,
                "Winner!",
                javax.swing.JOptionPane.INFORMATION_MESSAGE
            );
        } else {
            // Game continues - switch to the other player
            swapPlayer();
            
            // Ask the new current player to take their turn
            currentPlayer.doTurn();
        }
    }
    
    /**
     * Helper method to disable all GUI buttons when game ends
     * 
     * This prevents players from making moves after a winner is determined.
     */
    private void disableAllButtons() {
        // Get all components and disable buttons
        java.awt.Component[] components = frame.getContentPane().getComponents();
        for (java.awt.Component comp : components) {
            if (comp instanceof javax.swing.JPanel) {
                disablePanelButtons((javax.swing.JPanel) comp);
            }
        }
    }
    
    /**
     * Recursive helper to disable buttons in panels
     */
    private void disablePanelButtons(javax.swing.JPanel panel) {
        for (java.awt.Component comp : panel.getComponents()) {
            if (comp instanceof javax.swing.JButton) {
                comp.setEnabled(false);
            } else if (comp instanceof javax.swing.JPanel) {
                disablePanelButtons((javax.swing.JPanel) comp);
            }
        }
    }
}
