/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 * 
 */
package tuc.isse.projekt01;

import tuc.isse.projekt01.controller.FrameGame;
import tuc.isse.projekt01.controller.FramePlayer;
import tuc.isse.projekt01.controller.Player;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.ObservableBoard;
import tuc.isse.projekt01.view.DegreeFrame;

/**
 * Projekt 04, Task g: GameMain_Frame - Main Class for GUI Game
 * 
 * This is the main entry point for the GUI-based version of the 90 Grad game.
 * It initializes all necessary components and starts the game:
 * 
 * 1. Creates an ObservableBoard (model) with starting ball positions
 * 2. Creates a DegreeFrame (view) to display the game
 * 3. Creates two FramePlayer instances (controller) for white and black players
 * 4. Creates a FrameGame instance (controller) to manage game flow
 * 5. Registers the frame as an observer of the board for automatic GUI updates
 * 6. Starts the game with game.doGame()
 * 
 * The game then runs interactively through the GUI, with players clicking buttons
 * to select balls and directions. The Observer pattern ensures the GUI updates
 * automatically after each move, and the FrameGame controller manages turn switching
 * and game end detection.
 * 
 * This follows the Model-View-Controller pattern established in Task a.
 */
public class GameMain_Frame {
    
    public static void main(String[] args) {
        // Projekt 04, Task g: Initialize and start the GUI game
        
        // Create the observable board (Model)
        // This board will notify observers when balls are moved
        ObservableBoard board = new ObservableBoard();
        
        // Create the GUI frame (View)
        // This displays the game and handles user input through buttons
        DegreeFrame frame = new DegreeFrame(board);
        
        // Create two FramePlayer instances (Controller)
        // Each player handles their respective ball movements through GUI interaction
        Player whitePlayer = new FramePlayer(Color.WHITE, board, frame);
        Player blackPlayer = new FramePlayer(Color.BLACK, board, frame);
        
        // Create the FrameGame controller (Controller)
        // This manages the game flow, turn switching, and end game detection
        FrameGame game = new FrameGame(frame, board, whitePlayer, blackPlayer);
        
        // Register the frame as observer of the board
        // This ensures the GUI updates automatically when the board changes
        board.addObserver(frame);
        
        // Trigger initial GUI update to show starting positions
        board.notifyObserver();
        
        // Start the game
        // This asks the first player (white) to make their move by registering
        // them as ActionListener for the GUI buttons
        game.doGame();
    }
}
