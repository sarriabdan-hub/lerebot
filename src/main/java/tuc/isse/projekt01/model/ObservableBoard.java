/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01.model;

import java.util.Set;
import java.util.HashSet;

/**
 * Projekt 04, Task b: Observer Pattern - ObservableBoard Class
 * 
 * This class extends Board and implements the Observer pattern. It maintains a set
 * of BoardObserver instances and notifies them whenever the board state changes.
 * 
 * Key features:
 * - addObserver(): Registers a new observer
 * - removeObserver(): Unregisters an observer
 * - notifyObserver(): Notifies all registered observers by calling their update() method
 * - moveBall(): Overrides Board.moveBall() to automatically notify observers after each move
 * 
 * This enables automatic GUI updates and game state tracking without tight coupling
 * between the model (Board) and view (DegreeFrame) components.
 */
public class ObservableBoard extends Board {
    // Store all observers
    private Set<BoardObserver> observers;
    
    public ObservableBoard() {
        super();                     // call Board constructor
        observers = new HashSet<>(); // use Set (no duplicates)
    }
    
    /**
     * Table 09 Task b
     * Add, Remove, Notify observer
     * @param observer The observer to register for board updates
     */
    public void addObserver(BoardObserver observer) {
        observers.add(observer);
    }
    /**
     * Remove an observer from receiving board updates
     * @param observer The observer to unregister
     */
    public void removeObserver(BoardObserver observer) {
        observers.remove(observer);
    }
    public void notifyObserver() {
        for (BoardObserver observer : observers) {
            observer.update(this);
        }
    }
    /**
     * Override moveBall to add observer notification
     * @param color The color of the player making the move
     * @param columnIndex Column position of the ball to move
     * @param rowIndex Row position of the ball to move
     * @param direction Direction to move the ball in
     * @throws NotYourBallException If the ball doesn't belong to the player
     * @throws OutOfGameException If the move would push a ball out of bounds
     * @throws NotInRangeException If the position is outside the board
     */
    @Override
    public void moveBall(Color color, int columnIndex, int rowIndex, Direction direction)
            throws NotYourBallException, OutOfGameException, NotInRangeException {

        // First execute normal game logic
        super.moveBall(color, columnIndex, rowIndex, direction);

        //Then notify observers
        notifyObserver();
    }
}
