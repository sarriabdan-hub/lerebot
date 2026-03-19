/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01;

import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.ObservableBoard;
import tuc.isse.projekt01.view.DegreeFrame;

/**
 * Projekt 04, Task d: Test/Demo class for DegreeFrame GUI
 * 
 * This is a demonstration/test main class that shows the DegreeFrame in action.
 * It creates an ObservableBoard, displays it in a DegreeFrame, and performs
 * a series of automated moves to demonstrate the GUI updating via the Observer pattern.
 * 
 * NOTE: This is NOT the final GameMain_Frame from Task g.
 * Task g requires a complete game implementation with FramePlayer and FrameGame classes
 * to enable interactive gameplay through the GUI.
 */
public class GuiMain {
	public static void main(String[] args) {
		// Test for Table 09 Task d: use ObservableBoard
		ObservableBoard board = new ObservableBoard();

		DegreeFrame frame = new DegreeFrame(board);

		board.addObserver(frame);

		board.notifyObserver(); // Force initial update
		try {

            // Case 6 (Black wins) 
            board.moveBall(Color.WHITE, 3, 0, Direction.RIGHT);
            Thread.sleep(500);
            
            board.moveBall(Color.BLACK, 3, 6, Direction.UP);
            Thread.sleep(500);

            board.moveBall(Color.WHITE, 5, 0, Direction.DOWN);
            Thread.sleep(500);

            board.moveBall(Color.BLACK, 6, 4, Direction.LEFT);
            Thread.sleep(500);

            board.moveBall(Color.WHITE, 1, 4, Direction.DOWN);
            Thread.sleep(500);

            board.moveBall(Color.BLACK, 3, 2, Direction.UP);
            Thread.sleep(500);

            board.moveBall(Color.WHITE, 1, 6, Direction.RIGHT);
            Thread.sleep(500);

            board.moveBall(Color.BLACK, 3, 0, Direction.LEFT); // Winning move

        } catch (Exception e) {
            e.printStackTrace();
        }
        
	}
}