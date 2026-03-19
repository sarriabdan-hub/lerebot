/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.Winner;
import tuc.isse.projekt01.model.ObservableBoard;
import tuc.isse.projekt01.model.BoardObserver;

/**
 * Projekt 04, Task c: Testing the Observer Mechanism
 * 
 * This test class implements BoardObserver to verify that the observer pattern
 * works correctly. The tests ensure that:
 * - Observers are notified after ball movements
 * - Multiple observers can be registered and all receive notifications
 * - Observers are notified when a winner is determined
 * - Observers can be properly removed and stop receiving notifications
 * 
 * The test class itself acts as an observer and uses assertions within the
 * update() method to verify correct behavior.
 */
// Table 09 Task c: Extend tests
// implement BoardObserver
public class BoardTestProject4 implements BoardObserver {
    private int updateCount = 0;
    private Winner lastWinner = Winner.NONE;
    

    // use appropriate asserts in the update method
    @Override
    public void update(ObservableBoard board) {
    	updateCount ++;
    	lastWinner = board.getWinner();
    }
    
	// Test notification on movement
    @Test
    public void testObserverIsNotifiedAfterMove() throws Exception {

        ObservableBoard board = new ObservableBoard();

        // register this test as observer
        board.addObserver(this);

        // perform a legal move
        board.moveBall(Color.WHITE, 1, 0, Direction.DOWN);

        // check if update() was called
        assertEquals(1, updateCount);
        assertEquals(Winner.NONE, lastWinner);
    }
    
    // Test multiple observers
    @Test
    public void testMultipleObservers() throws Exception {

        ObservableBoard board = new ObservableBoard();

        BoardTestProject4 observer1 = new BoardTestProject4();
        BoardTestProject4 observer2 = new BoardTestProject4();

        board.addObserver(observer1);
        board.addObserver(observer2);

        board.moveBall(Color.BLACK, 3, 6, Direction.UP);

        assertEquals(1, observer1.updateCount);
        assertEquals(1, observer2.updateCount);
    }


    // Test winner triggers notification
    @Test
    public void testObserverOnWin() throws Exception {

        ObservableBoard board = new ObservableBoard();
        board.addObserver(this);

        // Force white to win by reaching center
        board.moveBall(Color.WHITE, 3, 0, Direction.DOWN);
        board.moveBall(Color.BLACK, 5, 6, Direction.UP);
        board.moveBall(Color.WHITE, 0, 0, Direction.DOWN);
        board.moveBall(Color.BLACK, 6, 4, Direction.UP);
        board.moveBall(Color.WHITE, 0, 5, Direction.RIGHT);
        board.moveBall(Color.BLACK, 4, 6, Direction.UP);
        board.moveBall(Color.WHITE, 0, 3, Direction.RIGHT);

        assertTrue(updateCount > 0);
        assertEquals(Winner.WHITE, lastWinner);
    }

    // Test removeObserver
    @Test
    public void testRemoveObserver() throws Exception {

        ObservableBoard board = new ObservableBoard();
        board.addObserver(this);
        board.removeObserver(this);

        board.moveBall(Color.BLACK, 3, 6, Direction.UP);

        assertEquals(0, updateCount);
    }

}

