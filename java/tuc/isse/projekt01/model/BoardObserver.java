/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01.model;

/**
 * Projekt 04, Task b: Observer Pattern - BoardObserver Interface
 * 
 * This interface is part of the Observer pattern implementation for the game board.
 * Classes implementing this interface can observe changes to the ObservableBoard
 * and receive notifications when the board state changes (e.g., after ball movements).
 * 
 * The update method is called by ObservableBoard.notifyObserver() to inform all
 * registered observers about board state changes.
 */
public interface BoardObserver {
	void update(ObservableBoard board);
}
